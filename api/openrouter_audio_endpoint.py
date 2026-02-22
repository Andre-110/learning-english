"""
音频对话端点 - 异步状态机模式

流程：
1. 前端 VAD 检测静默 → 发送音频
2. 后端语义判断 → 完整则处理，不完整则等待
3. 支持用户打断 AI、内容拼接

状态机：
- IDLE: 空闲，等待用户说话
- SPEAKING: 用户正在说话，累积音频
- TENTATIVE: 语义不完整，等待用户继续（5秒超时）
- PROCESSING: 正在处理（三轨并行）
- AI_SPEAKING: AI 正在回复
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
from datetime import datetime
from enum import Enum
import json
import base64
import asyncio
import time
import re
import concurrent.futures

from services.unified_processor import UnifiedProcessor, UserProfileUpdater, create_processor
from services.tts import TTSServiceFactory, EdgeTTSService
from services.deepgram_asr import DeepgramASR, DeepgramConfig
from services.doubao_asr import DoubaoASR, DoubaoASRConfig
from services.session_cache import get_session_cache, CachedSession
from services.connection_monitor import ConnectionMonitor
from config.settings import Settings
from config.constants import EVALUATION_CADENCE_TURNS, EVALUATION_AGGREGATE_TURNS
from storage.repository import RepositoryFactory
from services.utils.logger import get_logger
from services.utils.metrics_collector import metrics as metrics_collector, record_latency, record_request
from services.utils.timeline_logger import get_timeline_logger, record_timeline_event, finalize_round_timeline

logger = get_logger("api.openrouter_audio")
router = APIRouter(prefix="/ws", tags=["audio"])

settings = Settings()


def _aggregate_recent_user_texts(
    conversation_history: list,
    current_text: str,
    max_turns: int
) -> str:
    user_texts = [
        msg.get("content", "").strip()
        for msg in conversation_history
        if msg.get("role") == "user" and isinstance(msg.get("content"), str)
    ]
    if current_text:
        if not user_texts or user_texts[-1] != current_text:
            user_texts.append(current_text)
    if max_turns and max_turns > 0:
        user_texts = user_texts[-max_turns:]
    return " ".join([t for t in user_texts if t]).strip()

# ========== ASR 提供商配置 ==========
ASR_PROVIDER = settings.asr_provider.lower() if hasattr(settings, 'asr_provider') else "deepgram"
logger.info(f"[ASR] 使用提供商: {ASR_PROVIDER}")


def _should_use_streaming_asr() -> bool:
    """判断是否应该启用流式 ASR"""
    if not settings.use_streaming_asr:
        return False
    
    if ASR_PROVIDER == "doubao":
        # 豆包需要 app_key 和 access_key
        import os
        return bool(os.getenv("DOUBAO_ASR_APP_KEY")) and bool(os.getenv("DOUBAO_ASR_ACCESS_KEY"))
    elif ASR_PROVIDER == "deepgram":
        return bool(settings.deepgram_api_key)
    else:
        return False

# 全局单例
_processor = None
_tts_service = None

# ========== 会话状态枚举 ==========
class SessionState(str, Enum):
    IDLE = "idle"               # 空闲，等待用户说话
    SPEAKING = "speaking"       # 用户正在说话
    TENTATIVE = "tentative"     # 语义不完整，等待继续
    PROCESSING = "processing"   # 正在处理（三轨并行）
    AI_SPEAKING = "ai_speaking" # AI 正在回复

# ========== 配置常量 ==========
TENTATIVE_TIMEOUT_SECONDS = 5  # 语义不完整时等待用户继续的超时时间
EVAL_TIMEOUT_SECONDS = 60  # 评估超时时间
EVAL_MAX_CONCURRENT_PER_USER = 3  # 每个用户最大并发评估数
ASR_PREWARM_ADVANCE_MS = 700  # ASR 预热提前量（ms）- AI 说话快结束时初始化 Deepgram


def get_processor() -> UnifiedProcessor:
    """获取统一处理器（单例）"""
    global _processor
    if _processor is None:
        # 从 main.py 获取当前服务设置
        try:
            from api.main import _current_llm_service
            service_type = _current_llm_service
        except Exception:
            service_type = settings.llm_service
        
        logger.info(f"[单例] 创建 UnifiedProcessor (服务: {service_type})...")
        _processor = create_processor(service_type=service_type)
    return _processor


def get_tts_service():
    """获取 TTS 服务（单例）"""
    global _tts_service
    if _tts_service is None:
        provider = settings.tts_provider
        logger.info(f"[单例] 创建 TTSService (provider={provider})...")
        
        # 根据 provider 选择正确的参数
        if provider == "minimax":
            _tts_service = TTSServiceFactory.create(
                provider=provider,
                model=getattr(settings, 'minimax_tts_model', 'speech-2.6-hd'),
                default_voice=getattr(settings, 'minimax_tts_voice', 'male-qn-jingying')
            )
        else:
            _tts_service = TTSServiceFactory.create(
                provider=provider,
                model=getattr(settings, 'tts_model', 'gpt-4o-mini-tts'),
                default_voice=getattr(settings, 'tts_default_voice', 'alloy')
            )
    return _tts_service


def is_sentence_end(text: str) -> bool:
    """检查文本是否以句子结束符结尾"""
    return text.rstrip().endswith(('.', '!', '?', '。', '！', '？'))


async def safe_send_json(websocket: WebSocket, data: dict, timeout: float = 5.0) -> bool:
    """安全发送 JSON，超时或连接断开返回 False"""
    try:
        await asyncio.wait_for(websocket.send_json(data), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.warning(f"[WebSocket] 发送超时({timeout}s): {data.get('type', 'unknown')}")
        return False
    except Exception as e:
        if "1000" in str(e) or "closed" in str(e).lower():
            logger.debug(f"[WebSocket] 连接已关闭，跳过发送: {data.get('type', 'unknown')}")
        else:
            logger.warning(f"[WebSocket] 发送失败: {e}")
        return False


async def generate_conversation_summary_async(conversation_id: str, user_text: str, ai_text: str, websocket=None):
    """
    异步生成对话摘要（第一轮对话后调用）
    
    摘要用于侧边栏显示对话主题
    """
    try:
        from services.qwen_omni_audio import create_qwen_omni_service
        from storage.impl.supabase_repository import SupabaseConversationRepository
        
        # 构建对话内容
        conversation_text = f"User: {user_text[:100]}\nAI: {ai_text[:100]}"
        
        # 调用 LLM 生成摘要
        llm = create_qwen_omni_service()
        summary = llm.call_with_text(
            system_prompt="Generate a very short summary (5-10 Chinese characters) for this English learning conversation. Only output the summary, nothing else.",
            user_prompt=f"Summarize this conversation in 5-10 Chinese characters:\n\n{conversation_text}"
        )
        summary = summary.strip().strip('"').strip("'")[:20]
        
        # 保存到数据库
        conv_repo = SupabaseConversationRepository()
        conv_repo.client.table("conversations").update({
            "summary": summary
        }).eq("conversation_id", conversation_id).execute()
        
        logger.info(f"[摘要] 已生成: {conversation_id} -> {summary}")
        
        # 通知前端摘要已更新
        if websocket:
            try:
                await websocket.send_json({
                    "type": "summary_updated",
                    "conversation_id": conversation_id,
                    "summary": summary
                })
            except Exception as ws_err:
                logger.warning(f"发送摘要更新通知失败: {ws_err}")
        
    except Exception as e:
        logger.error(f"生成摘要失败: {e}")


@router.websocket("/openrouter-audio")
async def audio_chat(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None),
    conversation_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None)
):
    """
    音频对话 WebSocket 端点 - 真正的流式输出
    
    消息格式：
    客户端 → 服务端：
    - {"type": "start"} - 开始录音
    - 二进制数据 - 音频块
    - {"type": "audio_end"} - 音频结束
    - {"type": "ping"} - 心跳
    
    服务端 → 客户端：
    - {"type": "connected"} - 连接成功
    - {"type": "session_resumed"} - 会话恢复成功
    - {"type": "text_chunk", "text": "..."} - 流式文字片段
    - {"type": "audio_chunk", "data": "base64"} - TTS 音频块
    - {"type": "sentence_end", "sentence": "..."} - 一句话结束
    - {"type": "transcription", "text": "..."} - 用户语音转录
    - {"type": "evaluation", "data": {...}} - 评估结果
    - {"type": "done"} - 处理完成
    - {"type": "pong"} - 心跳响应
    """
    await websocket.accept()

    # ========== 指标：记录连接 ==========
    metrics_collector.connection_opened(user_id=user_id)

    processor = get_processor()
    tts_service = get_tts_service()
    user_repo = RepositoryFactory.create_user_repository()
    session_cache = get_session_cache()
    
    # ========== 生成或使用 session_id ==========
    if not session_id:
        import uuid
        session_id = conversation_id or str(uuid.uuid4())
    
    # ========== 尝试恢复会话 ==========
    restored_session: Optional[CachedSession] = session_cache.try_restore(session_id)
    is_restored = restored_session is not None
    
    # 加载用户画像
    user_profile = {}
    if is_restored:
        # 从恢复的会话中获取
        user_profile = restored_session.user_profile
        logger.info(f"[会话恢复] 使用缓存的用户画像: {user_id}, level={user_profile.get('cefr_level')}")
    elif user_id:
        db_profile = user_repo.get(user_id)
        if db_profile:
            user_profile = db_profile.dict()
            logger.info(f"加载用户画像: {user_id}, level={user_profile.get('cefr_level')}")
    
    # ========== 恢复或初始化对话历史 ==========
    if is_restored:
        conversation_history = restored_session.conversation_history.copy()
        round_counter = restored_session.round_counter
        logger.info(f"[会话恢复] 对话历史: {len(conversation_history)} 条, 轮次: {round_counter}")
    else:
        conversation_history = []
        round_counter = 0
    
    audio_format = "wav"

    # ========== 对话历史线程锁（交互线程读、主协程写）==========
    import threading
    history_lock = threading.Lock()
    
    # ========== 会话状态机上下文 ==========
    session_context = {
        "state": SessionState.IDLE,
        "accumulated_audio": [],        # 累积的音频数据（支持拼接）
        "accumulated_text": "",         # 累积的转录文本（TENTATIVE 状态）
        "tentative_task": None,         # 5秒超时任务
        "current_round_id": None,       # 当前轮次 ID
        "interaction_task": None,       # 交互轨任务（用于打断取消）
        "is_interrupted": False,        # 是否被打断
        "round_counter": round_counter, # 轮次计数器（可能从缓存恢复）
        # ========== 流式 ASR（支持 Deepgram 和豆包）==========
        "streaming_asr": None,          # 流式 ASR 实例（Deepgram 或豆包）
        "asr_provider": ASR_PROVIDER,   # ASR 提供商
        "prewarmed_asr": None,          # 预热的 ASR 连接
        "use_streaming_asr": _should_use_streaming_asr(),  # 是否启用流式 ASR
        "streaming_transcript": "",     # 流式转录累积结果
        "utterance_end_event": None,    # utterance_end 事件（用于触发处理）
        # 兼容性别名
        "deepgram_asr": None,           # 兼容旧代码
        # ========== 会话缓存相关 ==========
        "session_id": session_id,       # 会话 ID
        "user_id": user_id,             # 用户 ID
        "conversation_id": conversation_id,  # 对话 ID
        "user_profile": user_profile,   # 用户画像引用
        "conversation_history": conversation_history,  # 对话历史引用
        "created_at": time.time(),      # 创建时间
        "last_activity_at": time.time(),  # 最后活动时间
        # ========== 阶段 2：响应时间监控 ==========
        "session_start_time": time.time(),  # 会话开始时间（用于前 5 分钟监控）
        "latency_samples": [],              # 端到端延迟样本 [(turn, latency_ms)]
    }

    # ========== 后台任务追踪（防止 fire-and-forget 异常丢失）==========
    _background_tasks: set = set()

    def _track_task(coro, name: str = "background"):
        """创建并追踪后台任务，异常自动记录日志"""
        task = asyncio.create_task(coro)
        _background_tasks.add(task)
        def _on_done(t):
            _background_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.warning(f"[后台任务] {name} 失败: {exc}")
        task.add_done_callback(_on_done)
        return task

    # ========== 每个连接独立的评估队列管理 ==========
    eval_context = {
        "semaphore": asyncio.Semaphore(EVAL_MAX_CONCURRENT_PER_USER),
        "tasks": {},
        "counter": [0]
    }
    
    # ========== 连接监控（心跳 + 不活动检测）==========
    connection_monitor: Optional[ConnectionMonitor] = None
    
    try:
        loop = asyncio.get_event_loop()
        
        import queue
        import threading
        
        # 创建连接监控器
        async def on_inactivity_disconnect(duration: float):
            """不活动超时，断开连接"""
            logger.warning(f"[Monitor] 不活动超时断开: {session_id}, {duration:.1f}s")
            # 由外层 finally 处理断开
        
        connection_monitor = ConnectionMonitor(
            websocket=websocket,
            session_id=session_id,
            on_inactivity_disconnect=on_inactivity_disconnect
        )
        
        # 启动监控
        await connection_monitor.start()
        
        # ========== 检查是否是继续对话 ==========
        is_continue = False
        if conversation_id:
            # 验证 conversation_id 格式
            if not isinstance(conversation_id, str) or not conversation_id.strip():
                logger.error(f"[继续对话] 无效的 conversation_id: {conversation_id} (type: {type(conversation_id)})")
            else:
                try:
                    from storage.impl.supabase_repository import SupabaseConversationRepository
                    conv_repo = SupabaseConversationRepository()
                    # 查询该对话是否已有消息（严格过滤）
                    messages_result = conv_repo.client.table("messages").select("*").eq(
                        "conversation_id", conversation_id.strip()
                    ).order("timestamp", desc=False).execute()
                    
                    # 验证查询结果：检查所有消息的 conversation_id 是否一致
                    if messages_result.data and len(messages_result.data) > 0:
                        # 验证所有消息的 conversation_id 是否一致
                        mismatched = [msg for msg in messages_result.data if msg.get("conversation_id") != conversation_id.strip()]
                        if mismatched:
                            logger.error(f"[继续对话] ⚠️ 发现 conversation_id 不匹配的消息！期望: {conversation_id}, 实际: {[m.get('conversation_id') for m in mismatched[:3]]}")
                        
                        is_continue = True
                        # 加载历史对话到 conversation_history（只加载匹配的）
                        for msg in messages_result.data:
                            if msg.get("conversation_id") == conversation_id.strip():
                                conversation_history.append({
                                    "role": msg["sender_role"],
                                    "content": msg["content"]
                                })
                            else:
                                logger.warning(f"[继续对话] ⚠️ 跳过 conversation_id 不匹配的消息: {msg.get('conversation_id')}")
                        
                        logger.info(f"[继续对话] conversation_id={conversation_id}, 加载了 {len(conversation_history)} 条历史消息（查询到 {len(messages_result.data)} 条）")
                        # 调试：记录前3条历史消息的内容（避免日志过长）
                        if conversation_history:
                            preview = conversation_history[:3]
                            preview_str = ", ".join([f"{m['role']}: {m['content'][:50]}..." for m in preview])
                            logger.info(f"[继续对话] 历史消息预览: {preview_str}")
                except Exception as e:
                    logger.error(f"检查历史消息失败: {e}", exc_info=True)
        
        # 发送连接成功信号
        if is_restored:
            # 会话恢复成功
            await websocket.send_json({
                "type": "session_resumed",
                "session_id": session_id,
                "conversation_count": len(conversation_history),
                "round_count": session_context["round_counter"],
                "message": "Session restored successfully"
            })
            logger.info(f"[会话恢复] 连接成功, session_id={session_id}, 对话历史: {len(conversation_history)} 条")
            # 恢复的会话跳过初始问题
            is_continue = True
        else:
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "is_continue": is_continue
            })
            logger.info(f"[初始化] 连接成功, user_id={user_id}, conversation_id={conversation_id}, session_id={session_id}, is_continue={is_continue}")
        
        # ========== 如果是继续对话，跳过初始问题生成 ==========
        if is_continue:
            # 直接发送完成信号，前端已有历史消息
            await websocket.send_json({
                "type": "done",
                "latency": {"total": 0}
            })
            logger.info("[继续对话] 跳过初始问题，等待用户输入")
        else:
            # ========== 新对话：生成初始问题 ==========
            initial_question = ""
            has_audio = False
            chunk_queue = queue.Queue()
            
            def generate_initial_s2s():
                """使用 S2S 生成初始问题"""
                try:
                    for chunk in processor.generate_initial_question_stream(user_profile):
                        chunk_queue.put(("chunk", chunk))
                    chunk_queue.put(("done", None))
                except Exception as e:
                    logger.error(f"初始问题 S2S 错误: {e}")
                    chunk_queue.put(("error", str(e)))
            
            # 启动 S2S 线程
            thread = threading.Thread(target=generate_initial_s2s, daemon=True)
            thread.start()
            
            # 异步消费 S2S 输出
            while True:
                try:
                    msg_type, data = await loop.run_in_executor(
                        None, lambda: chunk_queue.get(timeout=60)
                    )
                    
                    if msg_type == "done":
                        break
                    elif msg_type == "error":
                        logger.error(f"初始问题错误: {data}")
                        break
                    elif msg_type == "chunk":
                        chunk = data
                        
                        # 处理文本
                        if chunk.get("text"):
                            initial_question += chunk["text"]
                            await websocket.send_json({
                                "type": "text_chunk",
                                "text": chunk["text"]
                            })
                        
                        # 处理音频（S2S）- Qwen-Omni 返回 PCM 格式
                        if chunk.get("audio"):
                            has_audio = True
                            logger.info(f"[初始S2S] 发送音频块, 大小: {len(chunk['audio'])}")
                            await websocket.send_json({
                                "type": "audio_chunk",
                                "data": chunk["audio"],
                                "format": "pcm"
                            })
                except Exception as e:
                    logger.error(f"初始问题队列错误: {e}")
                    break
            
            # 发送音频结束
            if has_audio:
                await websocket.send_json({"type": "audio_end"})
            
            logger.info(f"[初始化] 初始问题: {initial_question[:50]}...")
            
            # 将初始问题加入对话历史
            conversation_history.append({"role": "assistant", "content": initial_question})
            
            # 保存初始问题到数据库
            if conversation_id and initial_question:
                try:
                    from storage.impl.supabase_repository import SupabaseConversationRepository
                    conv_repo = SupabaseConversationRepository()
                    conv_repo.client.table("messages").insert({
                        "conversation_id": conversation_id,
                        "round_number": 0,
                        "sender_role": "assistant",
                        "content": initial_question,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "metadata": {"is_initial": True}
                    }).execute()
                    logger.info(f"[初始化] 初始问题已保存到数据库")
                except Exception as e:
                    logger.error(f"保存初始问题失败: {e}")
            
            # 生成中文翻译
            try:
                translation = await loop.run_in_executor(
                    None, lambda: processor.translate_only(initial_question)
                )
                if translation:
                    await websocket.send_json({
                        "type": "translation",
                        "text": translation
                    })
            except Exception as e:
                logger.error(f"初始问题翻译失败: {e}")
            
            # 发送初始化完成信号
            await websocket.send_json({
                "type": "done",
                "latency": {"total": 0}
            })
            
            logger.info("[初始化] 初始问题发送完成")
        
        # 主消息循环
        while True:
            try:
                message = await websocket.receive()
                
                if "text" in message:
                    try:
                        data = json.loads(message["text"])
                        msg_type = data.get("type")
                        
                        # 更新活动时间
                        session_context["last_activity_at"] = time.time()
                        if connection_monitor:
                            connection_monitor.update_activity()
                        
                        if msg_type == "start":
                            # ========== 用户开始说话 ==========
                            prev_state = session_context["state"]
                            logger.info(f"[状态机] 收到 start, 当前状态: {prev_state}")
                            
                            # ========== 场景判断 ==========
                            if prev_state == SessionState.AI_SPEAKING:
                                # 场景 1: 打断 AI 说话
                                logger.info("[状态机] 🛑 打断 AI 说话 → 开新对话")
                                session_context["is_interrupted"] = True
                                if session_context["interaction_task"]:
                                    session_context["interaction_task"].cancel()
                                await websocket.send_json({"type": "interrupt", "message": "用户打断"})
                                # 打断后开新对话
                                session_context["accumulated_audio"] = []
                                session_context["accumulated_text"] = ""
                                session_context["round_counter"] += 1
                                
                            elif prev_state == SessionState.PROCESSING:
                                # 场景 2: 打断正在处理中 → 保留上下文继续说（False Interruption 恢复）
                                logger.info("[状态机] 🔄 打断处理中 → 保留上下文继续")
                                session_context["is_interrupted"] = True
                                if session_context["interaction_task"]:
                                    session_context["interaction_task"].cancel()
                                await websocket.send_json({"type": "continue", "message": "用户继续说话"})
                                # ===== 关键：保留 accumulated_text，实现内容拼接 =====
                                # 1. 清空 accumulated_audio（新录音会重新开始）
                                # 2. 保留 accumulated_text（作为下次处理的前缀）
                                # 3. 不增加 round_counter（同一轮对话）
                                session_context["accumulated_audio"] = []
                                # 注意：不清空 accumulated_text
                                
                            else:
                                # 场景 3: 正常开始新对话 (IDLE 或 SPEAKING)
                                logger.info("[状态机] 🎙️ 开始新对话")
                                session_context["accumulated_audio"] = []
                                session_context["accumulated_text"] = ""
                                session_context["round_counter"] += 1
                            
                            # 生成新的 round_id
                            session_context["current_round_id"] = f"{conversation_id}_{session_context['round_counter']}" if conversation_id else f"msg_{session_context['round_counter']}"
                            
                            # 更新状态
                            session_context["state"] = SessionState.SPEAKING
                            session_context["is_interrupted"] = False
                            
                            # 通知前端录音开始
                            await websocket.send_json({
                                "type": "recording_started",
                                "message_round_id": session_context["current_round_id"]
                            })
                            
                            # ========== 初始化 Deepgram 流式 ASR ==========
                            if session_context["use_streaming_asr"]:
                                await init_deepgram_streaming(
                                    websocket=websocket,
                                    session_context=session_context,
                                    message_round_id=session_context["current_round_id"]
                                )
                            
                        elif msg_type == "audio_meta":
                            audio_format = data.get("format", "wav")
                            
                        elif msg_type == "audio_end":
                            # ========== 用户停止说话（静默触发）==========
                            if session_context["state"] == SessionState.SPEAKING and session_context["accumulated_audio"]:
                                logger.info(f"[状态机] 收到 audio_end, 音频块数: {len(session_context['accumulated_audio'])}")

                                await handle_audio_end(
                                    websocket=websocket,
                                    session_context=session_context,
                                    audio_format=audio_format,
                                    processor=processor,
                                    tts_service=tts_service,
                                    conversation_history=conversation_history,
                                    user_profile=user_profile,
                                    user_id=user_id,
                                    user_repo=user_repo,
                                    conversation_id=conversation_id,
                                    eval_context=eval_context,
                                    loop=loop
                                )

                        elif msg_type == "stop_audio":
                            # ========== 🔧 修复：处理前端 VAD 发送的 stop_audio ==========
                            # 前端 VAD 检测到用户说完后发送 stop_audio（不是 audio_end）
                            # 复用 handle_audio_end 逻辑
                            if session_context["state"] == SessionState.SPEAKING and session_context["accumulated_audio"]:
                                logger.info(f"[状态机] 收到 stop_audio, 音频块数: {len(session_context['accumulated_audio'])}")

                                await handle_audio_end(
                                    websocket=websocket,
                                    session_context=session_context,
                                    audio_format=audio_format,
                                    processor=processor,
                                    tts_service=tts_service,
                                    conversation_history=conversation_history,
                                    user_profile=user_profile,
                                    user_id=user_id,
                                    user_repo=user_repo,
                                    conversation_id=conversation_id,
                                    eval_context=eval_context,
                                    loop=loop
                                )
                            else:
                                logger.info(f"[状态机] 收到 stop_audio 但状态不匹配: state={session_context['state']}, audio_chunks={len(session_context['accumulated_audio'])}")
                        
                        elif msg_type == "interrupt":
                            # ========== 前端主动打断 ==========
                            logger.info("[状态机] 收到前端打断信号")
                            session_context["is_interrupted"] = True
                            if session_context["interaction_task"]:
                                session_context["interaction_task"].cancel()
                            if session_context["tentative_task"]:
                                session_context["tentative_task"].cancel()
                            session_context["state"] = SessionState.IDLE
                            await websocket.send_json({"type": "interrupt", "message": "用户打断"})
                        
                        elif msg_type == "ping":
                            # ========== 心跳响应 ==========
                            session_context["last_activity_at"] = time.time()
                            if connection_monitor:
                                connection_monitor.update_pong()
                                connection_monitor.update_activity()
                            await websocket.send_json({
                                "type": "pong",
                                "timestamp": data.get("timestamp"),
                                "server_time": time.time()
                            })
                        
                        elif msg_type == "close":
                            break
                            
                    except json.JSONDecodeError:
                        pass
                
                elif "bytes" in message:
                    # ========== 累积音频数据 ==========
                    if session_context["state"] == SessionState.SPEAKING:
                        audio_chunk = message["bytes"]
                        # 音频缓冲上限 10MB，防止弱网下内存溢出
                        total_audio_size = sum(len(c) for c in session_context["accumulated_audio"])
                        if total_audio_size + len(audio_chunk) > 10 * 1024 * 1024:
                            logger.warning(f"[状态机] 音频缓冲超过 10MB，丢弃新数据")
                        else:
                            session_context["accumulated_audio"].append(audio_chunk)
                        
                        # ========== Deepgram 流式 ASR：实时发送音频 ==========
                        asr = session_context.get("streaming_asr") or session_context.get("deepgram_asr")
                        if session_context["use_streaming_asr"] and asr:
                            try:
                                # 从 WAV 数据提取 PCM（跳过 WAV 头）
                                pcm_data = extract_pcm_from_wav_chunk(audio_chunk)
                                if pcm_data:
                                    await asr.send_audio(pcm_data)
                            except Exception as e:
                                logger.warning(f"[ASR] 发送音频失败: {e}")
                
            except WebSocketDisconnect:
                logger.info("WebSocket 断开")
                break
                
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}", exc_info=True)
        if connection_monitor:
            connection_monitor.record_anomaly("WEBSOCKET_ERROR", str(e))
    finally:
        # ========== 取消未完成的后台任务 ==========
        for task in list(_background_tasks):
            if not task.done():
                task.cancel()

        # ========== 停止连接监控 ==========
        if connection_monitor:
            await connection_monitor.stop()

        # ========== 指标：记录断开 ==========
        metrics_collector.connection_closed(user_id=user_id)
        
        # ========== 保存会话到缓存（支持断网重连）==========
        # 更新 session_context 中的引用，确保最新状态被缓存
        session_context["conversation_history"] = conversation_history
        session_context["user_profile"] = user_profile
        session_cache.disconnect(session_id, session_context)
        logger.info(f"[会话缓存] 已保存会话: {session_id}, 对话历史: {len(conversation_history)} 条")
        
        # 保存用户画像
        if user_id and user_profile:
            try:
                db_profile = user_repo.get(user_id)
                if db_profile:
                    from models.user import CEFRLevel, InterestTag
                    
                    # 更新简单字段
                    if 'overall_score' in user_profile:
                        db_profile.overall_score = user_profile['overall_score']
                    if 'strengths' in user_profile:
                        db_profile.strengths = user_profile['strengths']
                    if 'weaknesses' in user_profile:
                        db_profile.weaknesses = user_profile['weaknesses']
                    
                    # cefr_level 需要特殊处理（枚举类型）
                    if 'cefr_level' in user_profile:
                        level_str = user_profile['cefr_level']
                        if isinstance(level_str, str):
                            level_str = level_str.split('/')[0].strip()
                            try:
                                db_profile.cefr_level = CEFRLevel(level_str)
                            except ValueError:
                                pass
                    
                    # interests 需要转换为 InterestTag 对象
                    if 'interests' in user_profile and user_profile['interests']:
                        interest_strings = user_profile['interests']
                        
                        # 收集现有标签（处理可能是字符串或 InterestTag 的情况）
                        existing_tags = []
                        valid_interests = []
                        for interest in db_profile.interests:
                            if isinstance(interest, InterestTag):
                                existing_tags.extend(interest.tags)
                                valid_interests.append(interest)
                            elif isinstance(interest, dict):
                                # 字典格式，转换为 InterestTag
                                tags = interest.get('tags', [])
                                if tags:
                                    existing_tags.extend(tags)
                                    valid_interests.append(InterestTag(
                                        category=interest.get('category', 'general'),
                                        tags=tags
                                    ))
                            elif isinstance(interest, str):
                                existing_tags.append(interest)
                        
                        # 确保 interest_strings 都是字符串
                        new_tags = []
                        for t in interest_strings:
                            if isinstance(t, str) and t not in existing_tags:
                                new_tags.append(t)
                        
                        if new_tags:
                            # 添加到现有的 general 类别，或创建新的
                            general_interest = next(
                                (i for i in valid_interests if i.category == "general"),
                                None
                            )
                            if general_interest:
                                # 不用 set，直接去重
                                combined = general_interest.tags + new_tags
                                general_interest.tags = list(dict.fromkeys(combined))[-10:]
                                db_profile.interests = valid_interests
                            else:
                                db_profile.interests = valid_interests + [InterestTag(
                                    category="general",
                                    tags=new_tags[:10]
                                )]
                    
                    user_repo.save(db_profile)
                    logger.info(f"用户画像已保存: {user_id}")
            except Exception as e:
                logger.error(f"保存用户画像失败: {e}", exc_info=True)


async def handle_audio_end(
    websocket: WebSocket,
    session_context: dict,
    audio_format: str,
    processor: UnifiedProcessor,
    tts_service,
    conversation_history: list,
    user_profile: dict,
    user_id: Optional[str],
    user_repo,
    conversation_id: Optional[str],
    eval_context: dict,
    loop
):
    """
    处理音频结束（用户静默触发）
    
    流程：
    1. 流式 ASR 模式：停止 Deepgram，获取转录
    2. 检查音频/转录是否有效
    3. 触发处理
    """
    # 🆕 阶段 2：记录用户说完的时间（端到端延迟起点）
    user_audio_end_time = time.time()
    
    audio_data = b''.join(session_context["accumulated_audio"])
    
    # ========== 流式 ASR 模式：停止 Deepgram 获取转录 ==========
    streaming_transcript = ""
    if session_context["use_streaming_asr"] and session_context.get("deepgram_asr"):
        streaming_transcript = await stop_streaming_asr(session_context)
        logger.info(f"[状态机] Deepgram 流式转录: {streaming_transcript[:50] if streaming_transcript else '(empty)'}...")
    
    # ========== 拼接之前的 accumulated_text（False Interruption 恢复）==========
    # 如果用户在上次静默后继续说话（PROCESSING 被打断），accumulated_text 会保留
    if session_context.get("accumulated_text"):
        prev_text = session_context["accumulated_text"]
        combined_text = prev_text + " " + streaming_transcript.strip() if streaming_transcript.strip() else prev_text
        logger.info(f"[状态机] 📝 拼接转录: '{prev_text[:30]}...' + '{streaming_transcript[:30] if streaming_transcript else ''}...' → '{combined_text[:50]}...'")
        streaming_transcript = combined_text
    
    # 检查音频大小
    min_audio_size = 10 * 1024  # 10KB
    if len(audio_data) < min_audio_size:
        logger.warning(f"[状态机] 音频太小: {len(audio_data)} bytes，跳过")
        session_context["state"] = SessionState.IDLE
        await websocket.send_json({"type": "error", "message": "音频太短"})
        return
    
    logger.info(f"[状态机] 收到完整音频, 大小={len(audio_data)} bytes, round_id={session_context['current_round_id']}")
    
    # 直接进入处理状态
    session_context["state"] = SessionState.PROCESSING
    
    # 发送处理中状态（使用安全发送，连接可能已断开）
    if not await safe_send_json(websocket, {"type": "processing", "stage": "llm"}):
        logger.warning("[状态机] WebSocket 已断开，跳过处理")
        session_context["state"] = SessionState.IDLE
        return
    
    # ===== 防止重复处理：如果已有处理任务正在运行，先取消它 =====
    if session_context.get("interaction_task") and not session_context["interaction_task"].done():
        logger.warning("[状态机] ⚠️ 检测到已有处理任务正在运行，取消旧任务")
        session_context["interaction_task"].cancel()
        try:
            await session_context["interaction_task"]
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"[状态机] 取消旧任务时出错: {e}")
    
    # ===== 保存当前转录到 accumulated_text，用于可能的拼接 =====
    # 如果用户在处理期间继续说话，这个值会被保留
    session_context["accumulated_text"] = streaming_transcript
    
    # ===== 使用后台任务运行处理，让消息循环继续接收打断信号 =====
    async def run_processing():
        try:
            await process_audio_stream(
                websocket=websocket,
                audio_buffer=session_context["accumulated_audio"],
                audio_format=audio_format,
                processor=processor,
                tts_service=tts_service,
                conversation_history=conversation_history,
                user_profile=user_profile,
                user_id=user_id,
                user_repo=user_repo,
                conversation_id=conversation_id,
                eval_context=eval_context,
                session_context=session_context,
                streaming_transcript=streaming_transcript,
                user_audio_end_time=user_audio_end_time  # 🆕 传递延迟起点
            )
            
            # 处理成功完成，重置状态
            if not session_context.get("is_interrupted"):
                session_context["accumulated_audio"] = []
                session_context["accumulated_text"] = ""
                session_context["streaming_transcript"] = ""
                session_context["state"] = SessionState.IDLE
        except asyncio.CancelledError:
            logger.info("[处理] 任务被取消（用户继续说话）")
            # 被取消时，保留 accumulated_text 用于拼接
            # 但需要清空 accumulated_audio，因为新录音会重新开始
            session_context["accumulated_audio"] = []
        except Exception as e:
            logger.error(f"[处理] 任务异常: {e}")
            # 异常时清理状态，避免残留数据影响下次处理
            session_context["accumulated_audio"] = []
            session_context["accumulated_text"] = ""
            session_context["streaming_transcript"] = ""
            session_context["state"] = SessionState.IDLE
    
    # 创建后台任务并保存引用
    task = asyncio.create_task(run_processing())
    session_context["interaction_task"] = task


async def process_audio_stream(
    websocket: WebSocket,
    audio_buffer: list,
    audio_format: str,
    processor: UnifiedProcessor,
    tts_service,
    conversation_history: list,
    user_profile: dict,
    user_id: Optional[str],
    user_repo,
    conversation_id: Optional[str] = None,
    eval_context: Optional[dict] = None,
    session_context: Optional[dict] = None,  # 会话上下文（状态机）
    streaming_transcript: Optional[str] = None,  # Deepgram 流式转录结果
    user_audio_end_time: Optional[float] = None  # 🆕 用户说完时间（延迟监控）
):
    """
    处理用户音频 - 使用 S2S 流式输出（文字+音频同时流式）
    
    支持打断检测：在流式输出过程中检查 session_context["is_interrupted"]
    
    流程：
    1. 交互轨（S2S）- 流式返回文字和音频
    2. 评估轨 - 异步队列执行，不阻塞主流程
    3. 支持用户打断
    4. 如果有流式转录（Deepgram），直接使用，跳过转录轨
    """
    import queue
    import threading
    
    timings = {}
    total_start = time.time()
    round_number = len([m for m in conversation_history if m.get("role") == "user"]) + 1
    _msg_round_id = f"{conversation_id}_{round_number}" if conversation_id else f"msg_{round_number}"

    # ========== 时间轴：ASR 开始 ==========
    record_timeline_event(
        user_id=user_id or "anonymous",
        conversation_id=conversation_id or "unknown",
        round_id=round_number,
        event_type="asr_start",
        message_round_id=_msg_round_id
    )
    
    try:
        audio_data = b''.join(audio_buffer)
        if not audio_data:
            await websocket.send_json({"type": "error", "message": "音频为空"})
            return
        
        # 检查音频大小：WAV 16kHz mono 格式，小于 10KB 可能是噪音或空录音
        # 10KB ≈ 0.3秒的音频，正常说话至少需要 1-2 秒
        min_audio_size = 10 * 1024  # 10KB
        if len(audio_data) < min_audio_size:
            logger.warning(f"[处理] 音频太小: {len(audio_data)} bytes，可能是噪音或空录音，跳过处理")
            await websocket.send_json({"type": "error", "message": "音频太短，请重新录音"})
            return
        
        logger.info(f"[处理] 音频大小: {len(audio_data)} bytes")
        
        # 发送处理中状态
        await websocket.send_json({"type": "processing", "stage": "llm"})
        
        loop = asyncio.get_event_loop()
        
        # ========== 三轨并行启动 ==========
        # 转录轨：Qwen-Omni 语音→文本（不输出音频）- 完成后立即发送
        # 交互轨：Qwen-Omni S2S 语音→语音+文本 - 独立进行
        # 评估轨：Qwen-Omni 语音→评估（异步，独立转录+评估）- 在 done 后启动
        
        # 生成本轮消息 ID（用于前端关联）
        round_number = len([m for m in conversation_history if m.get("role") == "user"]) + 1
        message_round_id = f"{conversation_id}_{round_number}" if conversation_id else f"msg_{round_number}"
        
        async def run_transcription_async():
            """异步运行转录轨，流式发送转录结果"""
            full_text = ""
            chunk_queue = queue.Queue()
            
            def stream_transcription():
                """在线程中流式获取转录"""
                try:
                    for chunk in processor.transcribe_audio_stream(
                        audio_data=audio_data,
                        audio_format=audio_format
                    ):
                        if chunk:
                            chunk_queue.put(("chunk", chunk))
                    chunk_queue.put(("done", None))
                except Exception as e:
                    logger.error(f"转录轨流式错误: {e}")
                    chunk_queue.put(("error", str(e)))
            
            # 启动转录线程
            transcription_thread = threading.Thread(target=stream_transcription, daemon=True)
            transcription_thread.start()
            
            # 异步消费转录 chunk
            try:
                while True:
                    msg_type, data = await loop.run_in_executor(
                        None, lambda: chunk_queue.get(timeout=60)
                    )
                    
                    if msg_type == "done":
                        break
                    elif msg_type == "error":
                        logger.error(f"转录轨错误: {data}")
                        break
                    elif msg_type == "chunk":
                        full_text += data
                        # 流式发送转录 chunk
                        await websocket.send_json({
                            "type": "transcription_chunk",
                            "text": data,
                            "message_round_id": message_round_id
                        })
            except Exception as e:
                logger.error(f"转录轨队列错误: {e}")
            
            # 发送完整转录结果
            if full_text:
                await websocket.send_json({
                    "type": "transcription",
                    "text": full_text.strip(),
                    "message_round_id": message_round_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                logger.info(f"[转录轨] 流式完成: {full_text[:50]}...")
                return full_text.strip()
            else:
                logger.warning("[转录轨] 空结果")
                return ""
        
        # ========== 转录轨：如果有流式转录结果则跳过 ==========
        transcription_task = None
        if streaming_transcript:
            # 使用 Deepgram 流式转录结果，跳过转录轨
            logger.info(f"[转录轨] 使用 Deepgram 流式转录: {streaming_transcript[:50]}...")
            # 发送完整转录结果
            await websocket.send_json({
                "type": "transcription",
                "text": streaming_transcript.strip(),
                "message_round_id": message_round_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "deepgram"  # 标记来源
            })
        else:
            # 启动转录轨（异步任务，不阻塞）
            transcription_task = asyncio.create_task(run_transcription_async())
            logger.info("[转录轨] 启动")
        
        # ========== 评估轨准备（与转录轨、交互轨并行）==========
        # 从 eval_context 获取评估队列管理变量
        if eval_context is None:
            eval_context = {"semaphore": asyncio.Semaphore(3), "tasks": {}, "counter": [0]}
        eval_semaphore = eval_context["semaphore"]
        eval_tasks = eval_context["tasks"]
        
        # 顺序号用于前端排序
        eval_context["counter"][0] += 1
        current_order = eval_context["counter"][0]
        
        async def run_evaluation_async():
            """
            评估轨 - 只负责评估，不负责保存消息
            
            职责：
            1. 调用评估 API
            2. 发送评估结果给前端
            3. 更新用户画像（分数/等级）
            4. 更新对话评分
            """
            eval_start = time.time()
            current_queue_size = len(eval_tasks)
            logger.info(f"[评估轨] 并行启动, message_round_id={message_round_id}, 当前队列: {current_queue_size}/{EVAL_MAX_CONCURRENT_PER_USER}")

            # 评分节奏控制：非指定轮次跳过评估
            if EVALUATION_CADENCE_TURNS > 1 and (current_order % EVALUATION_CADENCE_TURNS) != 0:
                logger.info(f"[评估轨] 节奏跳过, message_round_id={message_round_id}, order={current_order}")
                try:
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "cadence"
                    })
                except Exception as e:
                    logger.debug(f"[评估轨] 发送跳过通知失败: {e}")
                if message_round_id in eval_tasks:
                    del eval_tasks[message_round_id]
                return

            # 聚合最近 N 轮用户输入（包含当前轮）
            current_transcription = ""
            if streaming_transcript:
                current_transcription = streaming_transcript.strip()
            elif transcription_task:
                try:
                    current_transcription = await asyncio.wait_for(transcription_task, timeout=10)
                except Exception:
                    current_transcription = ""
            aggregated_transcription = _aggregate_recent_user_texts(
                conversation_history,
                current_transcription,
                EVALUATION_AGGREGATE_TURNS
            )
            if not aggregated_transcription:
                logger.warning(f"[评估轨] 聚合转录为空，跳过评估, message_round_id={message_round_id}")
                try:
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "empty_transcription"
                    })
                except Exception as e:
                    logger.debug(f"[评估轨] 发送跳过通知失败: {e}")
                if message_round_id in eval_tasks:
                    del eval_tasks[message_round_id]
                return
            
            # 尝试非阻塞获取信号量
            try:
                await asyncio.wait_for(eval_semaphore.acquire(), timeout=0.1)
            except asyncio.TimeoutError:
                logger.warning(f"[评估轨] 队列已满，跳过评估, message_round_id={message_round_id}")
                try:
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "queue_full"
                    })
                except Exception as e:
                    logger.debug(f"[评估轨] 发送跳过通知失败: {e}")
                if message_round_id in eval_tasks:
                    del eval_tasks[message_round_id]
                return
            
            try:
                # 评估 API 调用 - 使用聚合后的转录（综合最近 N 轮）
                evaluation = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: processor.evaluate_only(
                            transcription=aggregated_transcription,
                            conversation_history=None,  # 无上下文评估
                            user_profile=user_profile
                        )
                    ),
                    timeout=EVAL_TIMEOUT_SECONDS
                )
                
                eval_time = time.time() - eval_start
                logger.info(f"[评估轨] 完成, 耗时: {eval_time:.2f}s")
                
                # 更新用户画像
                if evaluation.get("overall_score") is not None:
                    from services.unified_processor import ProcessingResult
                    eval_result = ProcessingResult(
                        transcription=evaluation.get("transcription", ""),
                        evaluation=evaluation,
                        interests=evaluation.get("interests", []),
                        ai_feedback="",
                        next_question="",
                        full_response=""
                    )
                    UserProfileUpdater.update(user_profile, eval_result)
                    logger.info(f"[画像] 更新: 分数={user_profile.get('overall_score')}, 等级={user_profile.get('cefr_level')}")
                    
                    # 更新对话评分
                    if conversation_id:
                        try:
                            from storage.impl.supabase_repository import SupabaseConversationRepository
                            conv_repo = SupabaseConversationRepository()
                            score = evaluation.get("overall_score", 0)
                            calculated_level = UserProfileUpdater._score_to_cefr(score)
                            conv_repo.client.table("conversations").update({
                                "cefr_level": calculated_level,
                                "overall_score": score
                            }).eq("conversation_id", conversation_id).execute()
                        except Exception as e:
                            logger.error(f"更新对话评分失败: {e}")
                
                # 发送评估结果
                score = evaluation.get("overall_score", 0)
                calculated_level = UserProfileUpdater._score_to_cefr(score)
                evaluation_with_correct_level = evaluation.copy()
                evaluation_with_correct_level["cefr_level"] = calculated_level
                
                try:
                    await websocket.send_json({
                        "type": "evaluation",
                        "data": evaluation_with_correct_level,
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "latency": round(eval_time, 2)
                    })
                    logger.info(f"[评估轨] 结果已推送, message_round_id={message_round_id}")
                except Exception as e:
                    logger.warning(f"发送评估失败: {e}")
                
            except asyncio.TimeoutError:
                eval_time = time.time() - eval_start
                logger.warning(f"[评估轨] 超时跳过, message_round_id={message_round_id}, 已执行: {eval_time:.2f}s")
                try:
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "timeout"
                    })
                except Exception as e:
                    logger.debug(f"[评估轨] 发送跳过通知失败: {e}")
                
            except Exception as e:
                logger.warning(f"[评估轨] 失败: {e}, message_round_id={message_round_id}")
                try:
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "error"
                    })
                except Exception as e:
                    logger.debug(f"[评估轨] 发送跳过通知失败: {e}")
                
            finally:
                eval_semaphore.release()
                if message_round_id in eval_tasks:
                    del eval_tasks[message_round_id]
                logger.info(f"[评估轨] 任务结束, message_round_id={message_round_id}")
        
        # 启动评估轨（与转录轨并行）
        eval_task = asyncio.create_task(run_evaluation_async())
        eval_tasks[message_round_id] = eval_task
        logger.info(f"[评估轨] 异步任务已创建, message_round_id={message_round_id}")

        # ========== 时间轴：ASR 结束 / LLM 开始 ==========
        record_timeline_event(
            user_id=user_id or "anonymous",
            conversation_id=conversation_id or "unknown",
            round_id=round_number,
            event_type="asr_end",
            message_round_id=_msg_round_id
        )
        record_timeline_event(
            user_id=user_id or "anonymous",
            conversation_id=conversation_id or "unknown",
            round_id=round_number,
            event_type="llm_start",
            message_round_id=_msg_round_id
        )
        
        # ========== 启动交互轨 ==========
        full_response = ""
        current_sentence = ""
        has_audio = False
        chunk_queue = queue.Queue()
        
        def stream_interaction():
            """在线程中运行交互轨"""
            try:
                chunk_count = 0
                # 快照对话历史，避免线程读写竞争
                with history_lock:
                    history_snapshot = list(conversation_history)
                # 调试：记录传递给交互轨的历史对话
                logger.info(f"[交互轨] conversation_id={conversation_id}, 历史对话长度={len(history_snapshot)}")
                if history_snapshot:
                    preview = history_snapshot[-3:]  # 最近3条
                    preview_str = ", ".join([f"{m.get('role', 'unknown')}: {str(m.get('content', ''))[:50]}..." for m in preview])
                    logger.info(f"[交互轨] 历史对话预览: {preview_str}")

                # 如果有 ASR 转录，使用文本接口（豆包ASR→GPT-4o→MiniMax 链路）
                if streaming_transcript:
                    for chunk in processor.interact_text_stream(
                        transcription=streaming_transcript,
                        conversation_history=history_snapshot,
                        user_profile=user_profile
                    ):
                        chunk_count += 1
                        chunk_queue.put(("chunk", chunk))
                    logger.info(f"[交互轨] 文本模式流式完成, 共 {chunk_count} 个 chunk")
                    chunk_queue.put(("done", None))
                    return

                # 否则使用音频接口（fallback）
                for chunk in processor.interact_stream(
                    audio_data=audio_data,
                    audio_format=audio_format,
                    conversation_history=history_snapshot,
                    user_profile=user_profile
                ):
                    chunk_count += 1
                    chunk_queue.put(("chunk", chunk))
                logger.info(f"[交互轨] 流式完成, 共 {chunk_count} 个 chunk")
                chunk_queue.put(("done", None))
            except Exception as e:
                import traceback
                logger.error(f"交互轨错误: {e}\n{traceback.format_exc()}")
                chunk_queue.put(("error", str(e)))
        
        # 启动交互轨
        interaction_thread = threading.Thread(target=stream_interaction, daemon=True)
        interaction_thread.start()
        logger.info("[交互轨] 启动")
        
        # 更新会话状态为 AI_SPEAKING
        if session_context:
            session_context["state"] = SessionState.AI_SPEAKING
        
        # 🆕 阶段 2：延迟监控 - 首个音频块时间
        first_audio_chunk_time = None
        
        # 异步消费交互轨输出（流式）
        while True:
            # ========== 打断检测 ==========
            if session_context and session_context.get("is_interrupted"):
                logger.info("[交互轨] 检测到打断，停止输出")
                break
            
            try:
                msg_type, data = await loop.run_in_executor(
                    None, lambda: chunk_queue.get(timeout=0.5)  # 短超时，便于打断检测
                )
                
                if msg_type == "done":
                    break
                elif msg_type == "error":
                    logger.error(f"交互轨错误: {data}")
                    break
                elif msg_type == "chunk":
                    chunk = data  # Dict with "text" and "audio"
                    
                    # 处理文本
                    text_chunk = chunk.get("text")
                    if text_chunk:
                        # ========== 时间轴：LLM 首 token ==========
                        if not full_response:
                            record_timeline_event(
                                user_id=user_id or "anonymous",
                                conversation_id=conversation_id or "unknown",
                                round_id=round_number,
                                event_type="llm_first_token",
                                message_round_id=_msg_round_id
                            )
                        full_response += text_chunk
                        current_sentence += text_chunk
                        if not await safe_send_json(websocket, {
                            "type": "text_chunk",
                            "text": text_chunk
                        }):
                            break
                    
                    # 处理音频（S2S）- Qwen-Omni 返回 PCM 格式
                    audio_chunk = chunk.get("audio")
                    if audio_chunk:
                        # ========== 时间轴：TTS 首块 ==========
                        if first_audio_chunk_time is None:
                            first_audio_chunk_time = time.time()
                            record_timeline_event(
                                user_id=user_id or "anonymous",
                                conversation_id=conversation_id or "unknown",
                                round_id=round_number,
                                event_type="tts_first_chunk",
                                message_round_id=_msg_round_id
                            )
                        has_audio = True
                        if not await safe_send_json(websocket, {
                            "type": "audio_chunk",
                            "data": audio_chunk,
                            "format": "pcm"
                        }):
                            break
                    
                    # 检查句子结束
                    if text_chunk and is_sentence_end(current_sentence):
                        await safe_send_json(websocket, {
                            "type": "sentence_end",
                            "sentence": current_sentence.strip()
                        })
                        current_sentence = ""
                        
            except Exception as e:
                import queue as q
                if isinstance(e, q.Empty):
                    # 短超时，继续循环检查打断
                    continue
                else:
                    logger.error(f"交互轨队列错误: {type(e).__name__}: {e}")
                break
        
        # 处理剩余文本
        if current_sentence.strip():
            await websocket.send_json({
                "type": "sentence_end",
                "sentence": current_sentence.strip()
            })
        
        # 发送音频结束
        if has_audio:
            await websocket.send_json({"type": "audio_end"})
        else:
            # 回退到 TTS（只发送音频，文字已通过交互轨发送）
            logger.info("[TTS回退] 生成 TTS 音频...")
            if full_response.strip():
                await send_tts_only(websocket, tts_service, full_response.strip())
        
        timings['interaction'] = time.time() - total_start

        # ========== 时间轴：LLM 结束 / TTS 结束 ==========
        record_timeline_event(
            user_id=user_id or "anonymous",
            conversation_id=conversation_id or "unknown",
            round_id=round_number,
            event_type="llm_end",
            message_round_id=_msg_round_id
        )
        record_timeline_event(
            user_id=user_id or "anonymous",
            conversation_id=conversation_id or "unknown",
            round_id=round_number,
            event_type="tts_end",
            message_round_id=_msg_round_id
        )
        
        # 检查是否被打断
        was_interrupted = session_context and session_context.get("is_interrupted")
        if was_interrupted:
            logger.info(f"[处理] 交互轨被打断, 已输出: {full_response[:30]}...")
        else:
            logger.info(f"[处理] 交互轨完成: {timings['interaction']:.2f}s, 回复: {full_response[:50]}...")
        
        # 🆕 阶段 2：计算端到端延迟（用户说完 → 首个音频块）
        if session_context and user_audio_end_time and first_audio_chunk_time:
            latency_ms = int((first_audio_chunk_time - user_audio_end_time) * 1000)
            session_start = session_context.get("session_start_time", 0)
            elapsed_minutes = (time.time() - session_start) / 60.0 if session_start else 0
            
            # 只监控前 5 分钟
            if elapsed_minutes <= 5:
                turn = session_context.get("round_counter", 0)
                session_context.setdefault("latency_samples", []).append((turn, latency_ms))
                
                # 计算均值
                samples = session_context["latency_samples"]
                avg_latency = sum(s[1] for s in samples) / len(samples) if samples else 0
                
                logger.info(f"[延迟监控] 轮次={turn}, 延迟={latency_ms}ms, "
                           f"前5分钟均值={avg_latency:.0f}ms ({len(samples)}样本)")
        
        # ========== 翻译轨已移除，改为按需翻译（用户点击翻译按钮时调用 /api/translate）==========
        
        # ========== 等待转录轨完成，获取 transcription ==========
        transcription = ""
        if streaming_transcript:
            # 使用 Deepgram 流式转录
            transcription = streaming_transcript.strip()
            logger.info(f"[主流程] 使用 Deepgram 流式转录: {transcription[:50] if transcription else '(empty)'}...")
        elif transcription_task:
            # 等待转录轨完成
            try:
                transcription = await asyncio.wait_for(transcription_task, timeout=10)
                if not transcription:
                    transcription = ""
                logger.info(f"[主流程] 转录轨结果: {transcription[:50] if transcription else '(empty)'}...")
            except asyncio.TimeoutError:
                logger.warning("[主流程] 转录轨超时，使用空转录")
            except Exception as e:
                logger.error(f"[主流程] 等待转录轨失败: {e}")
        
        # ========== 更新对话历史（主流程负责）==========
        with history_lock:
            if transcription:
                conversation_history.append({"role": "user", "content": transcription})
            if full_response:
                conversation_history.append({"role": "assistant", "content": full_response})

            # 保留最近 10 轮
            if len(conversation_history) > 20:
                conversation_history[:] = conversation_history[-20:]
        
        # ========== 保存消息到数据库（主流程负责）==========
        if conversation_id and (transcription or full_response):
            # 验证 conversation_id
            if not isinstance(conversation_id, str) or not conversation_id.strip():
                logger.error(f"[消息] ⚠️ 无效的 conversation_id，跳过保存: {conversation_id}")
            else:
                try:
                    from storage.impl.supabase_repository import SupabaseConversationRepository
                    conv_repo = SupabaseConversationRepository()
                    
                    messages_to_save = []
                    clean_conversation_id = conversation_id.strip()
                    
                    if transcription:
                        messages_to_save.append({
                            "conversation_id": clean_conversation_id,
                            "round_number": round_number,
                            "sender_role": "user",
                            "content": transcription,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "metadata": {}
                        })
                    if full_response:
                        messages_to_save.append({
                            "conversation_id": clean_conversation_id,
                            "round_number": round_number,
                            "sender_role": "assistant",
                            "content": full_response,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "metadata": {}
                        })
                    
                    if messages_to_save:
                        conv_repo.client.table("messages").insert(messages_to_save).execute()
                        logger.info(f"[消息] 已保存 {len(messages_to_save)} 条消息到数据库, conversation_id={clean_conversation_id}")
                except Exception as e:
                    logger.error(f"保存消息失败: {e}", exc_info=True)
        
        # ========== 第一轮对话后自动生成摘要 ==========
        user_msg_count = len([m for m in conversation_history if m.get("role") == "user"])
        if conversation_id and user_msg_count == 1 and transcription:
            try:
                logger.info(f"[摘要] 触发生成: {conversation_id}")
                _track_task(generate_conversation_summary_async(conversation_id, transcription, full_response, websocket), "摘要生成")
            except Exception as e:
                logger.error(f"启动摘要生成失败: {e}")
        
        # ========== 交互轨+翻译轨完成，发送 done 信号 ==========
        total_time = time.time() - total_start
        logger.info(f"[性能] 主流程耗时: {total_time:.2f}s | 交互: {timings.get('interaction', 0):.2f}s")
        
        # ========== ASR 预热：在 AI 回复完成后初始化 Deepgram 连接 ==========
        # 这样用户下次说话时连接已就绪，节省约 700ms 的建连延迟
        if session_context and session_context.get("use_streaming_asr"):
            _track_task(prewarm_deepgram_asr(session_context), "ASR预热")
        
        # 发送完成信号（评估轨已并行启动，不需要等待）
        await websocket.send_json({
            "type": "done",
            "latency": {
                "total": round(total_time, 2),
                "interaction": round(timings.get('interaction', 0), 2)
            }
        })

        # ========== 时间轴：结束本轮 + 记录延迟指标 ==========
        round_data = finalize_round_timeline(
            user_id=user_id or "anonymous",
            conversation_id=conversation_id or "unknown",
            round_id=round_number
        )
        if round_data:
            latencies = round_data.get("latencies", {})
            for key, val in latencies.items():
                record_latency(f"openrouter.{key}", val)
        record_latency("openrouter.total", total_time * 1000)
        record_latency("openrouter.interaction", timings.get('interaction', 0) * 1000)
        record_request("openrouter", "/ws/openrouter-audio", success=True)
        
    except Exception as e:
        logger.error(f"处理音频错误: {e}", exc_info=True)
        record_request("openrouter", "/ws/openrouter-audio", success=False)
        await websocket.send_json({"type": "error", "message": str(e)})


# ========== 旧评估轨代码已删除，评估轨现在与转录轨、交互轨并行启动 ==========
async def generate_sentence_tts(websocket: WebSocket, tts_service, sentence: str):
    """为单个句子生成 TTS 并优化发送"""
    try:
        # 检查是否是 Edge TTS（支持流式）
        if isinstance(tts_service, EdgeTTSService):
            # Edge TTS 支持流式，边生成边发送
            await _stream_tts_audio(websocket, tts_service, sentence)
        else:
            # OpenAI TTS 等批量模式：优化块大小和发送策略
            audio_data = await tts_service._text_to_speech_async(
                text=sentence,
                voice=getattr(settings, 'tts_default_voice', 'alloy')
            )
            
            # 优化：更小的块大小（2KB），快速响应，减少卡顿
            chunk_size = 2 * 1024  # 2KB 块，平衡网络效率和播放流畅度
            total_chunks = (len(audio_data) + chunk_size - 1) // chunk_size
            
            # 快速连续发送所有块，不添加延迟
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                await websocket.send_json({
                    "type": "audio_chunk",
                    "data": base64.b64encode(chunk).decode()
                })
                # 不添加延迟，让音频块连续发送，前端 Web Audio API 会处理播放时序
        
    except Exception as e:
        logger.error(f"TTS 句子失败: {e}")


async def _stream_tts_audio(websocket: WebSocket, tts_service, sentence: str):
    """流式生成和发送 TTS 音频（Edge TTS）"""
    try:
        import edge_tts
        
        voice = getattr(settings, 'tts_default_voice', 'en-US-JennyNeural')
        if not voice or voice not in ['en-US-JennyNeural', 'alloy', 'nova', 'shimmer']:
            # 如果使用的是 OpenAI TTS 的语音名，转换为 Edge TTS
            voice = 'en-US-JennyNeural'
        
        # 创建流式通信对象
        communicate = edge_tts.Communicate(
            sentence, 
            voice,
            rate="+0%",
            volume="+0%",
            pitch="+0Hz"
        )
        
        # 流式接收并立即发送音频块
        buffer = b""
        chunk_size = 2 * 1024  # 2KB 块大小
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer += chunk["data"]
                
                # 当缓冲区达到块大小时，发送并清空
                while len(buffer) >= chunk_size:
                    chunk_to_send = buffer[:chunk_size]
                    buffer = buffer[chunk_size:]
                    
                    await websocket.send_json({
                        "type": "audio_chunk",
                        "data": base64.b64encode(chunk_to_send).decode()
                    })
        
        # 发送剩余的音频数据
        if buffer:
            await websocket.send_json({
                "type": "audio_chunk",
                "data": base64.b64encode(buffer).decode()
            })
            
    except Exception as e:
        logger.error(f"流式 TTS 失败: {e}")
        # 回退到批量模式
        audio_data = await tts_service._text_to_speech_async(
            text=sentence,
            voice=getattr(settings, 'tts_default_voice', 'alloy')
        )
        chunk_size = 2 * 1024
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            await websocket.send_json({
                "type": "audio_chunk",
                "data": base64.b64encode(chunk).decode()
            })


async def send_tts_only(websocket: WebSocket, tts_service, text: str):
    """
    只发送 TTS 音频，不发送文字（文字已通过交互轨发送）
    """
    # 按句子分割
    sentences = re.split(r'(?<=[.!?])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    for sentence in sentences:
        await generate_sentence_tts(websocket, tts_service, sentence)
    
    # 发送音频结束
    await websocket.send_json({"type": "audio_end"})


async def stream_text_with_tts(websocket: WebSocket, tts_service, text: str, is_initial: bool = False):
    """
    流式发送文字和 TTS（用于初始问题等已生成的文本）
    
    逐字发送文字，每句话生成 TTS
    对于包含中文翻译的文本（格式：English (中文)），只朗读英文部分
    """
    # 分离英文和中文翻译
    # 格式：English text (中文翻译)
    english_text = text
    chinese_text = ""
    
    # 检查是否包含括号中的中文翻译
    match = re.match(r'^(.+?)\s*[（(](.+?)[）)]$', text)
    if match:
        english_text = match.group(1).strip()
        chinese_text = match.group(2).strip()
    
    # 按句子分割英文部分
    sentences = re.split(r'(?<=[.!?])\s*', english_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    for sentence in sentences:
        # 逐字发送文字（模拟流式效果）
        for char in sentence:
            await websocket.send_json({
                "type": "text_chunk",
                "text": char
            })
            await asyncio.sleep(0.01)  # 减小延迟从 20ms 到 10ms，加快文字显示速度
        
        # 发送句子结束
        await websocket.send_json({
            "type": "sentence_end",
            "sentence": sentence
        })
        
        # 只朗读英文部分 - 立即开始生成 TTS，不等待
        await generate_sentence_tts(websocket, tts_service, sentence)
    
    # 如果有中文翻译，单独发送（不朗读）
    if chinese_text:
        await websocket.send_json({
            "type": "translation",
            "text": chinese_text
        })


# ========== Deepgram 流式 ASR 辅助函数 ==========

def extract_pcm_from_wav_chunk(wav_data: bytes) -> bytes:
    """
    从 WAV 数据中提取 PCM 音频
    
    WAV 格式：44 字节头 + PCM 数据
    如果数据没有 WAV 头（纯 PCM），直接返回
    """
    if not wav_data or len(wav_data) < 44:
        return wav_data
    
    # 检查是否是 WAV 格式（RIFF 头）
    if wav_data[:4] == b'RIFF':
        # 跳过 44 字节的 WAV 头
        return wav_data[44:]
    else:
        # 已经是纯 PCM 数据
        return wav_data


async def init_streaming_asr(
    websocket: WebSocket,
    session_context: dict,
    message_round_id: str
):
    """
    初始化流式 ASR 连接（支持 Deepgram 和豆包）
    
    根据 asr_provider 配置选择不同的 ASR 服务。
    """
    provider = session_context.get("asr_provider", "deepgram")
    
    try:
        # 检查是否有预热的连接（阶段 3 改进：复用已建立的 WebSocket 连接）
        prewarmed_asr = session_context.get("prewarmed_asr")
        prewarm_connected = session_context.get("prewarm_connected", False)
        
        if prewarmed_asr and prewarm_connected and prewarmed_asr.is_connected:
            # 🆕 阶段 3：复用已建立的连接，只更新回调，不重新建立连接
            logger.info(f"[{provider}] ✅ 复用预热的 WebSocket 连接（解决首句丢失）")
            session_context["streaming_asr"] = prewarmed_asr
            session_context["deepgram_asr"] = prewarmed_asr  # 兼容
            session_context["prewarmed_asr"] = None
            session_context["prewarm_connected"] = False
            session_context["reuse_prewarm_connection"] = True  # 标记复用
        elif prewarmed_asr:
            # 有预热实例但连接未建立或已断开
            logger.info(f"[{provider}] 复用预热实例（连接未就绪，将重新建立）")
            session_context["streaming_asr"] = prewarmed_asr
            session_context["deepgram_asr"] = prewarmed_asr  # 兼容
            session_context["prewarmed_asr"] = None
            session_context["reuse_prewarm_connection"] = False
        else:
            # 创建新的 ASR 实例
            if provider == "doubao":
                import os
                config = DoubaoASRConfig(
                    app_key=os.getenv("DOUBAO_ASR_APP_KEY"),
                    access_key=os.getenv("DOUBAO_ASR_ACCESS_KEY"),
                )
                session_context["streaming_asr"] = DoubaoASR(config)
            else:
                config = DeepgramConfig(
                    api_key=settings.deepgram_api_key,
                    model=settings.deepgram_model,
                    language="en"
                )
                session_context["streaming_asr"] = DeepgramASR(config)
            
            session_context["deepgram_asr"] = session_context["streaming_asr"]  # 兼容
        
        # 重置转录结果
        session_context["streaming_transcript"] = ""
        
        # 创建 utterance_end 事件
        session_context["utterance_end_event"] = asyncio.Event()
        
        # 定义回调函数
        async def on_transcript(text: str, is_final: bool):
            """处理转录结果"""
            if is_final and text:
                if session_context["streaming_transcript"]:
                    session_context["streaming_transcript"] += " " + text
                else:
                    session_context["streaming_transcript"] = text
            
            await websocket.send_json({
                "type": "transcription_chunk",
                "text": text,
                "is_final": is_final,
                "message_round_id": message_round_id
            })
        
        async def on_utterance_end():
            """处理 utterance_end 事件"""
            logger.info(f"[{provider}] utterance_end 触发")
            session_context["utterance_end_event"].set()
        
        async def on_error(error):
            logger.error(f"[{provider}] 错误: {error}")
        
        # 🆕 阶段 3：检查是否复用已连接的预热连接
        if session_context.get("reuse_prewarm_connection"):
            # 复用已建立的连接，只更新回调
            asr = session_context["streaming_asr"]
            if hasattr(asr, 'update_callbacks'):
                asr.update_callbacks(
                    on_transcript=on_transcript,
                    on_utterance_end=on_utterance_end,
                    on_error=on_error
                )
                logger.info(f"[{provider}] ✅ 复用预热连接，已更新回调，round_id={message_round_id}")
                started = True
            else:
                # 回退到重新连接
                started = await asr.start_stream(
                    on_transcript=on_transcript,
                    on_utterance_end=on_utterance_end,
                    on_error=on_error
                )
            session_context["reuse_prewarm_connection"] = False
        else:
            # 正常启动流式连接
            started = await session_context["streaming_asr"].start_stream(
                on_transcript=on_transcript,
                on_utterance_end=on_utterance_end,
                on_error=on_error
            )
        
        if started:
            logger.info(f"[{provider}] 流式 ASR 已启动, round_id={message_round_id}")
        else:
            logger.error(f"[{provider}] 流式 ASR 启动失败")
            session_context["streaming_asr"] = None
            session_context["deepgram_asr"] = None
            
    except Exception as e:
        logger.error(f"[{provider}] 初始化失败: {e}")
        session_context["streaming_asr"] = None
        session_context["deepgram_asr"] = None


# 兼容旧函数名
async def init_deepgram_streaming(websocket, session_context, message_round_id):
    return await init_streaming_asr(websocket, session_context, message_round_id)


async def prewarm_streaming_asr(session_context: dict):
    """
    ASR 预热：提前初始化 ASR 连接并建立 WebSocket 连接
    
    改进（阶段 3）：解决首句丢失问题
    - 提前创建 ASR 实例
    - 提前建立 WebSocket 连接（减少首句识别延迟）
    - 设置音频缓冲区（缓存用户开始说话前的音频）
    """
    if not session_context["use_streaming_asr"]:
        return
    
    provider = session_context.get("asr_provider", "deepgram")
    
    try:
        logger.info(f"[{provider}] 开始预热 ASR 连接（提前建立 WebSocket）...")
        
        if provider == "doubao":
            import os
            config = DoubaoASRConfig(
                app_key=os.getenv("DOUBAO_ASR_APP_KEY"),
                access_key=os.getenv("DOUBAO_ASR_ACCESS_KEY"),
            )
            asr = DoubaoASR(config)
            
            # 🆕 阶段 3 改进：提前建立 WebSocket 连接
            # 这样用户开始说话时，连接已经就绪，减少首句丢失
            prewarm_connected = await asr.start_stream(
                on_transcript=None,  # 预热时不需要回调
                on_utterance_end=None,
                on_error=None
            )
            
            if prewarm_connected:
                logger.info(f"[{provider}] ✅ ASR 预热连接已建立（WebSocket 就绪）")
            else:
                logger.warning(f"[{provider}] ⚠️ ASR 预热连接失败，将在首次使用时重试")
            
            session_context["prewarmed_asr"] = asr
            session_context["prewarm_connected"] = prewarm_connected
        else:
            config = DeepgramConfig(
                api_key=settings.deepgram_api_key,
                model=settings.deepgram_model,
                language="en"
            )
            asr = DeepgramASR(config)
            
            # Deepgram 也提前建立连接
            prewarm_connected = await asr.start_stream(
                on_transcript=None,
                on_utterance_end=None,
                on_error=None
            )
            
            session_context["prewarmed_asr"] = asr
            session_context["prewarm_connected"] = prewarm_connected
            logger.info(f"[{provider}] ASR 预热完成，连接状态: {prewarm_connected}")
        
    except Exception as e:
        logger.warning(f"[{provider}] ASR 预热失败: {e}")
        session_context["prewarmed_asr"] = None
        session_context["prewarm_connected"] = False
        session_context["prewarmed_asr"] = None


# 兼容旧函数名
async def prewarm_deepgram_asr(session_context):
    return await prewarm_streaming_asr(session_context)


async def stop_streaming_asr(session_context: dict) -> str:
    """
    停止流式 ASR 并返回完整转录
    """
    transcript = ""
    provider = session_context.get("asr_provider", "deepgram")
    
    asr = session_context.get("streaming_asr") or session_context.get("deepgram_asr")
    if asr:
        try:
            transcript = await asr.stop_stream()
            logger.info(f"[{provider}] 流式 ASR 已停止, 转录: {transcript[:50] if transcript else '(空)'}...")
        except Exception as e:
            logger.warning(f"[{provider}] 停止流式 ASR 失败: {e}")
        finally:
            session_context["streaming_asr"] = None
            session_context["deepgram_asr"] = None
    
    if not transcript and session_context.get("streaming_transcript"):
        transcript = session_context["streaming_transcript"]
    
    return transcript


# 兼容旧函数名
async def stop_deepgram_streaming(session_context):
    return await stop_streaming_asr(session_context)
