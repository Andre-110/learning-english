"""
GPT-4o 三段链路 WebSocket 端点

只替换交互轨（ASR → LLM → TTS），评估轨继续使用 Qwen-Omni。

架构：
- 交互轨：GPT-4o 三段链路（gpt-4o-transcribe → gpt-4o → gpt-4o-mini-tts）
- 评估轨：Qwen-Omni（原有的 UnifiedProcessor.evaluate_audio_no_context）
- 翻译轨：原有逻辑
- 摘要生成：原有逻辑

WebSocket 消息格式与 openrouter_audio_endpoint.py 完全兼容。
"""
import json
import asyncio
import time
import queue
import threading
import os
import base64
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from config.constants import (
    EVALUATION_TIMEOUT,
    MAX_CONCURRENT_EVALUATIONS,
    HOT_CONTENT_GREETING_TIMEOUT,
    EVALUATION_CADENCE_TURNS,
    EVALUATION_AGGREGATE_TURNS,
    USE_PVAD,
    PVAD_THRESHOLD,
)
from services.gpt4o_pipeline import GPT4oPipeline, create_gpt4o_pipeline, PerformanceMetrics
from services.unified_processor import UnifiedProcessor, UserProfileUpdater, create_processor
from services.content_injector import ContentInjector, get_content_injector
from services.summary_service import generate_conversation_summary
from services.tracks.evaluation import EvaluationTrack
from storage.repository import RepositoryFactory
from services.utils.structured_logger import get_logger, set_user_context, log_user, log_perf
from services.utils.metrics_collector import (
    metrics as metrics_collector,
    connection_opened, connection_closed,
    conversation_started, conversation_ended,
    record_request, record_latency, increment
)
from services.utils.timeline_logger import (
    get_timeline_logger,
    record_timeline_event,
    finalize_round_timeline
)
from models.conversation_memory import (
    ConversationMemory,
    get_or_create_memory,
    clear_user_memory
)
from prompts.templates import (
    get_pipeline_system_prompt_with_memory,
    get_pipeline_user_prompt_with_memory
)
from services.hot_content_pool import (
    create_hot_content_context,
    add_to_pool,
    select_best_hot_content,
    mark_used as mark_hot_content_used,
    get_pool_stats
)

# 🆕 语义完整性检测（使用大模型）
from services.semantic_completeness import get_semantic_checker

# 🆕 pVAD 噪音过滤
from services.pvad_filter import get_pvad_filter

# 🆕 用户画像缓存（减少 Supabase 延时）
from services.user_cache import (
    get_user_cache,
    get_new_user_greeting,
    get_default_user_profile,
)
from config.settings import settings as app_settings


# 🆕 流式 ASR（支持多提供商）
try:
    from services.deepgram_asr import DeepgramASR, DeepgramConfig, create_deepgram_asr
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False

try:
    from services.doubao_asr import DoubaoASR, DoubaoASRConfig, create_doubao_asr
    DOUBAO_AVAILABLE = True
except ImportError:
    DOUBAO_AVAILABLE = False

# 🆕 热备份连接池
try:
    from services.doubao_asr_pool import DoubaoASRPool, PoolConfig, create_asr_pool
    DOUBAO_POOL_AVAILABLE = True
except ImportError:
    DOUBAO_POOL_AVAILABLE = False

# 🆕 是否使用热备份连接池（双连接模式）
# 兼容 .env 中的 use_asr_pool / USE_ASR_POOL（Settings 做了大小写不敏感解析）
USE_ASR_POOL = bool(getattr(app_settings, "use_asr_pool", False)) or (os.environ.get("USE_ASR_POOL", "false").lower() == "true")

# 获取 ASR 提供商配置
ASR_PROVIDER = os.environ.get("ASR_PROVIDER", "deepgram").lower()

logger = get_logger("api.gpt4o_pipeline")
router = APIRouter(prefix="/ws", tags=["gpt4o-pipeline"])

# 🆕 会话缓存（支持断线重连恢复）
# 格式: {session_key: {"conversation_history": [...], "user_profile": {...}, ...}}
SESSION_CACHE: Dict[str, Dict[str, Any]] = {}
SESSION_CACHE_TTL = 300  # 5分钟过期


# 🆕 热点池函数已移至 services/hot_content_pool.py
# select_best_hot_content → select_best_hot_content
# mark_hot_content_used → mark_hot_content_used


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


def get_session_cache_key(user_id: str, conversation_id: str) -> str:
    """生成会话缓存键"""
    return f"{user_id or 'anonymous'}:{conversation_id or 'new'}"


def cache_session_state(cache_key: str, state: Dict[str, Any]):
    """缓存会话状态（用于断线重连）"""
    SESSION_CACHE[cache_key] = {
        **state,
        "cached_at": time.time()
    }
    logger.info(f"[会话缓存] 已缓存: {cache_key}, history_len={len(state.get('conversation_history', []))}")


def get_cached_session(cache_key: str) -> Optional[Dict[str, Any]]:
    """获取缓存的会话状态"""
    if cache_key not in SESSION_CACHE:
        return None
    
    cached = SESSION_CACHE[cache_key]
    cached_at = cached.get("cached_at", 0)
    
    # 检查是否过期
    if time.time() - cached_at > SESSION_CACHE_TTL:
        del SESSION_CACHE[cache_key]
        logger.info(f"[会话缓存] 已过期: {cache_key}")
        return None
    
    return cached


def clear_session_cache(cache_key: str):
    """清除会话缓存"""
    if cache_key in SESSION_CACHE:
        del SESSION_CACHE[cache_key]
        logger.info(f"[会话缓存] 已清除: {cache_key}")


def create_wav_from_pcm(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """
    将 PCM 数据转换为 WAV 格式
    
    Args:
        pcm_data: 16-bit signed little-endian PCM 数据
        sample_rate: 采样率（默认 16000）
    
    Returns:
        完整的 WAV 文件数据
    """
    import struct
    
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_data)
    
    # 创建 WAV 文件头（44 字节）
    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',                    # ChunkID
        36 + data_size,             # ChunkSize
        b'WAVE',                    # Format
        b'fmt ',                    # Subchunk1ID
        16,                         # Subchunk1Size (PCM)
        1,                          # AudioFormat (PCM = 1)
        num_channels,               # NumChannels
        sample_rate,                # SampleRate
        byte_rate,                  # ByteRate
        block_align,                # BlockAlign
        bits_per_sample,            # BitsPerSample
        b'data',                    # Subchunk2ID
        data_size                   # Subchunk2Size
    )
    
    return wav_header + pcm_data

# 全局单例
_pipeline: Optional[GPT4oPipeline] = None
_processor: Optional[UnifiedProcessor] = None
_content_injector: Optional[ContentInjector] = None

# 配置常量（从 config.constants 导入）
EVAL_TIMEOUT_SECONDS = EVALUATION_TIMEOUT
EVAL_MAX_CONCURRENT_PER_USER = MAX_CONCURRENT_EVALUATIONS
GREETING_HOT_CONTENT_TIMEOUT_SEC = HOT_CONTENT_GREETING_TIMEOUT

# 热点内容配置
CONTENT_INJECTION_ENABLED = True  # 是否启用热点注入

# 🆕 流式 ASR 配置（支持 Deepgram / 豆包）
# 启用流式 ASR：边说边识别，节省 500ms~1s
# 🔧 修复：同时检查 Deepgram 和豆包的可用性
STREAMING_ASR_ENABLED = DEEPGRAM_AVAILABLE or DOUBAO_AVAILABLE  # ✅ 支持多 ASR 提供商
STREAMING_ASR_LANGUAGE = "en"  # 流式 ASR 语言

# 评估轨单例
_evaluation_track: Optional[EvaluationTrack] = None


def get_pipeline() -> GPT4oPipeline:
    """获取 GPT-4o Pipeline（单例）- 用于交互轨"""
    global _pipeline
    if _pipeline is None:
        logger.info("[单例] 创建 GPT4oPipeline (交互轨)...")
        _pipeline = create_gpt4o_pipeline()
    return _pipeline


def get_processor() -> UnifiedProcessor:
    """获取 UnifiedProcessor（单例）- 用于评估轨"""
    global _processor
    if _processor is None:
        logger.info("[单例] 创建 UnifiedProcessor (评估轨)...")
        _processor = create_processor(service_type="qwen-omni")
    return _processor


def get_injector() -> ContentInjector:
    """获取 ContentInjector（单例）- 用于热点内容注入"""
    global _content_injector
    if _content_injector is None:
        logger.info("[单例] 创建 ContentInjector (热点轨)...")
        _content_injector = get_content_injector()
    return _content_injector


def get_evaluation_track() -> EvaluationTrack:
    """获取 EvaluationTrack（单例）- 用于三阶段评估"""
    global _evaluation_track
    if _evaluation_track is None:
        logger.info("[单例] 创建 EvaluationTrack (评估轨)...")
        processor = get_processor()  # 使用 UnifiedProcessor 作为语音评估器
        _evaluation_track = EvaluationTrack(voice_evaluator=processor)
    return _evaluation_track


async def _generate_memory_summary_async(memory: ConversationMemory, websocket=None):
    """
    异步生成记忆摘要
    
    当记忆管理器标记 summary_pending=True 时调用
    """
    try:
        messages_to_summarize = memory.get_messages_for_summary()
        if not messages_to_summarize:
            memory.summary_pending = False
            return
        
        # 调用摘要服务
        new_summary = await generate_conversation_summary(
            messages_to_summarize,
            memory.session_summary
        )
        
        if new_summary:
            memory.set_session_summary(new_summary)
            logger.info(f"[Memory] 摘要已更新: {new_summary[:50]}...")
            
            # 可选：通知前端摘要已更新
            if websocket:
                try:
                    await websocket.send_json({
                        "type": "memory_summary_updated",
                        "summary_preview": new_summary[:100]
                    })
                except Exception:
                    pass  # WebSocket 可能已断开
    except Exception as e:
        logger.error(f"[Memory] 摘要生成失败: {e}")
        memory.summary_pending = False


async def generate_conversation_summary_async(conversation_id: str, user_text: str, ai_text: str, websocket=None):
    """异步生成对话摘要"""
    try:
        from services.qwen_omni_audio import create_qwen_omni_service
        from storage.impl.supabase_repository import SupabaseConversationRepository

        conversation_text = f"User: {user_text[:100]}\nAI: {ai_text[:100]}"

        llm = create_qwen_omni_service()
        summary = llm.call_with_text(
            system_prompt="Generate a very short summary (5-10 Chinese characters) for this English learning conversation. Only output the summary, nothing else.",
            user_prompt=f"Summarize this conversation in 5-10 Chinese characters:\n\n{conversation_text}"
        )
        summary = summary.strip().strip('"').strip("'")[:20]

        conv_repo = SupabaseConversationRepository()
        conv_repo.client.table("conversations").update({
            "summary": summary
        }).eq("conversation_id", conversation_id).execute()

        logger.info(f"[摘要] 已生成: {conversation_id} -> {summary}")

        if websocket:
            try:
                await websocket.send_json({
                    "type": "summary_updated",
                    "conversation_id": conversation_id,
                    "summary": summary
                })
            except (WebSocketDisconnect, RuntimeError):
                # WebSocket 可能已断开，忽略发送错误
                pass
    except Exception as e:
        logger.error(f"生成摘要失败: {e}")


@router.websocket("/gpt4o-pipeline")
@router.websocket("/conversation")  # 🆕 兼容旧前端路径，替换旧的 conversation 端点
async def gpt4o_pipeline_chat(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None),
    conversation_id: Optional[str] = Query(None)
):
    """
    GPT-4o 三段链路 WebSocket 端点

    交互轨使用 GPT-4o 三段链路，评估轨使用 Qwen-Omni
    消息格式与 openrouter_audio_endpoint 完全兼容
    """
    await websocket.accept()

    pipeline = get_pipeline()
    processor = get_processor()
    user_repo = RepositoryFactory.create_user_repository()
    
    # 🆕 生成会话缓存键（用于断线重连）
    session_cache_key = get_session_cache_key(user_id, conversation_id)
    is_session_resumed = False

    # 🆕 优化：使用缓存加载用户画像，避免 Supabase 跨境延时
    user_profile = {}
    is_new_user = False
    user_cache = get_user_cache()
    
    if user_id:
        # 先查缓存
        cached = user_cache.get(user_id)
        
        if cached is not None:
            # 缓存命中
            if cached.is_new_user:
                # 已知新用户，使用默认值，跳过数据库查询
                user_profile = get_default_user_profile()
                is_new_user = True
                logger.info(f"[UserCache] 命中已知新用户: {user_id}, 跳过 Supabase 查询")
            else:
                # 老用户，使用缓存的画像
                user_profile = cached.profile or {}
                logger.info(f"[UserCache] 命中缓存: {user_id}, level={user_profile.get('cefr_level')}")
        else:
            # 缓存未命中，查数据库
            db_profile = user_repo.get(user_id)
            if db_profile:
                user_profile = db_profile.dict()
                user_cache.set(user_id, user_profile, is_new_user=False)
                logger.info(f"加载用户画像: {user_id}, level={user_profile.get('cefr_level')}")
            else:
                # 新用户，使用默认值
                user_profile = get_default_user_profile()
                is_new_user = True
                user_cache.set(user_id, None, is_new_user=True)
                logger.info(f"[新用户] {user_id}, 使用默认画像, 跳过后续查询")
    
    # 🆕 记录连接打开（监控指标），带用户名
    username = user_profile.get("username") or user_profile.get("name") or "Unknown"
    connection_opened(user_id, username=username)
    record_request("websocket", "/ws/gpt4o-pipeline", success=True)
        
    # 🆕 P5: 后台预热用户的 interests（不阻塞，仅老用户）
    user_interests = user_profile.get('interests', [])
    if user_interests and CONTENT_INJECTION_ENABLED and not is_new_user:
        async def _warmup_user_interests():
            """后台预热用户兴趣话题"""
            try:
                injector = get_injector()
                cefr_level = user_profile.get('cefr_level', 'B1')
                for interest in user_interests[:3]:  # 最多预热3个
                    if isinstance(interest, str):
                        # 后台搜索并缓存，不等待结果
                        await injector.fetch_for_topic_async(interest, cefr_level)
                        logger.info(f"[热点轨] 预热用户兴趣: {interest}")
            except Exception as e:
                logger.debug(f"[热点轨] 预热失败（不影响使用）: {e}")
        
        # 启动后台任务，不阻塞连接流程
        asyncio.create_task(_warmup_user_interests())
        logger.info(f"[热点轨] 启动后台预热: {user_interests[:3]}")

    # 🆕 初始化对话记忆管理器（三层记忆架构）
    memory = get_or_create_memory(user_id or "anonymous", user_profile)
    logger.info(f"[Memory] 初始化记忆管理器, user_id={user_id}, stats={memory.get_stats()}")

    # 🆕 检查是否有缓存的会话（断线重连）
    cached_session = get_cached_session(session_cache_key)
    if cached_session:
        conversation_history = cached_session.get("conversation_history", [])
        is_session_resumed = True
        logger.info(f"[会话恢复] 从缓存恢复会话: {session_cache_key}, history_len={len(conversation_history)}")
        # 🔧 修复：不再立即清除缓存，改为在连接稳定后清除
        # 如果连接再次断开，缓存仍然可用于下次恢复
        _session_cache_cleared = False
    else:
        conversation_history = []
        
        # 🆕 新对话：加载上次对话摘要（跨对话记忆）
        # 优化：新用户跳过此查询，避免无效的 Supabase 调用
        if user_id and not is_new_user:
            try:
                last_summary_data = user_repo.get_last_conversation_summary(user_id)
                if last_summary_data and last_summary_data.get("summary"):
                    memory.set_session_summary(last_summary_data["summary"], is_cross_session=True)
                    if last_summary_data.get("topics"):
                        memory.discussed_topics = last_summary_data["topics"]
                    logger.info(f"[跨对话摘要] 已加载: {user_id}, 摘要长度={len(last_summary_data['summary'])}, 话题={last_summary_data.get('topics', [])}")
            except Exception as e:
                logger.warning(f"[跨对话摘要] 加载失败: {e}")
        elif is_new_user:
            logger.info(f"[新用户] {user_id}, 跳过跨对话摘要查询")
    audio_buffer = []
    audio_format = "wav"
    is_recording = False

    # 评估队列管理
    eval_context = {
        "semaphore": asyncio.Semaphore(EVAL_MAX_CONCURRENT_PER_USER),
        "tasks": {},
        "counter": [0]
    }

    # 🆕 打断机制状态（学习自 UserGenie）
    interrupt_state = {
        "is_speaking": False,        # AI 是否正在说话（播放音频）
        "interrupt_event": None,     # 中断事件（用于终止流水线）
        "current_task": None,        # 当前处理任务（用于取消）
    }

    # 🆕 连接健壮性上下文（学习自 UserGenie）
    # 配置常量
    HEARTBEAT_TIMEOUT_SECONDS = 60          # 心跳超时（秒）
    INACTIVITY_WARNING_SECONDS = 120        # 不活动警告阈值（2分钟）
    INACTIVITY_DISCONNECT_SECONDS = 300     # 不活动断开阈值（5分钟）
    MONITOR_INTERVAL_SECONDS = 10           # 监控检查间隔（秒）
    MAX_ANOMALY_EVENTS = 50                 # 最大异常事件数
    
    robustness_context = {
        "last_activity_time": time.time(),   # 最后活动时间
        "last_ping_time": None,              # 最后收到 ping 的时间
        "last_pong_time": None,              # 最后收到 pong 的时间（后端发 ping 时用）
        "session_start_time": time.time(),   # 会话开始时间
        "reconnect_count": 0,                # 重连次数
        "inactivity_warning_sent": False,    # 是否已发送不活动警告
        "anomaly_events": [],                # 异常事件列表
        "monitor_task": None,                # 监控任务
        "is_monitoring": False,              # 是否正在监控
    }
    
    def record_anomaly(event_type: str, message: str, data: Any = None):
        """记录异常事件"""
        event = {
            "type": event_type,
            "message": message,
            "timestamp": time.time(),
            "data": data
        }
        robustness_context["anomaly_events"].append(event)
        # 保持列表大小
        if len(robustness_context["anomaly_events"]) > MAX_ANOMALY_EVENTS:
            robustness_context["anomaly_events"] = robustness_context["anomaly_events"][-MAX_ANOMALY_EVENTS:]
        logger.warning(f"[异常记录] {event_type}: {message}")
    
    async def connection_monitor():
        """后台连接监控任务"""
        robustness_context["is_monitoring"] = True
        logger.info("[连接监控] 启动")
        
        try:
            while robustness_context["is_monitoring"]:
                await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
                
                if not robustness_context["is_monitoring"]:
                    break
                
                current_time = time.time()
                last_activity = robustness_context["last_activity_time"]
                inactive_duration = current_time - last_activity
                
                # 检查心跳超时
                last_ping = robustness_context.get("last_ping_time")
                if last_ping and (current_time - last_ping) > HEARTBEAT_TIMEOUT_SECONDS:
                    record_anomaly("HEARTBEAT_TIMEOUT", f"心跳超时 {HEARTBEAT_TIMEOUT_SECONDS} 秒")
                
                # 检查不活动
                if inactive_duration > INACTIVITY_DISCONNECT_SECONDS:
                    # 超过 5 分钟不活动，断开连接
                    record_anomaly("INACTIVITY_DISCONNECT", f"不活动 {inactive_duration:.0f} 秒，断开连接")
                    try:
                        await websocket.send_json({
                            "type": "inactivity_disconnect",
                            "duration": inactive_duration,
                            "message": "连接因不活动被断开"
                        })
                        await websocket.close()
                    except Exception:
                        pass
                    break
                    
                elif inactive_duration > INACTIVITY_WARNING_SECONDS and not robustness_context["inactivity_warning_sent"]:
                    # 超过 2 分钟不活动，发送警告
                    robustness_context["inactivity_warning_sent"] = True
                    record_anomaly("INACTIVITY_WARNING", f"不活动 {inactive_duration:.0f} 秒")
                    try:
                        await websocket.send_json({
                            "type": "inactivity_warning",
                            "duration": inactive_duration,
                            "message": "连接即将因不活动被断开"
                        })
                    except Exception:
                        pass
                        
        except asyncio.CancelledError:
            logger.info("[连接监控] 被取消")
        except Exception as e:
            logger.error(f"[连接监控] 异常: {e}")
        finally:
            robustness_context["is_monitoring"] = False
            logger.info("[连接监控] 停止")

    # 🆕 热点内容上下文（使用共享模块 services/hot_content_pool.py）
    hot_content_context = create_hot_content_context()

    # 🆕 记忆上下文（传递给 process_audio_stream）
    memory_context = {
        "memory": memory,
        "user_id": user_id or "anonymous"
    }

    # 🆕 Deepgram 流式 ASR 上下文（已禁用，保留结构兼容）
    deepgram_context = {
        "asr": None,              # DeepgramASR 实例
        "is_enabled": STREAMING_ASR_ENABLED,
        "transcript_buffer": "",  # 累积的转录结果（Final 结果）
        "last_interim_text": "",  # 🆕 最新临时结果（兜底用）
        "is_processing": False,   # 是否正在处理（防止重复触发）
        # 🆕 延迟确认机制
        "pending_llm_task": None,       # 待执行的 LLM 任务（asyncio.Task）
        "confirmation_delay_ms": 500,   # 确认窗口时长（毫秒）
        "accumulated_transcript": "",   # 累积的完整转录（跨多次 utterance_end）
        "audio_buffer": [],             # 🆕 音频缓冲（用于连接未建立时的暂存）
        # 🆕 防重复发送（参考 UserGenie）
        "last_utterance_text": "",      # 上次发送的 utterance_end 文本
        "last_utterance_time": 0,       # 上次发送的时间戳
        # 🆕 pVAD 噪音过滤（USE_PVAD=true 时启用）
        "pvad_filter": get_pvad_filter(USE_PVAD, PVAD_THRESHOLD),
    }
    
    # 🆕 GPT-4o Pipeline 上下文（语义检测 + 累积 + 打断 + 轮次管理）
    pipeline_context = {
        "accumulated_transcript": "",   # 累积的转录（语义不完整时）
        "is_processing": False,         # LLM 是否正在处理
        "llm_task": None,               # 当前 LLM 处理任务
        "llm_cancelled": False,         # LLM 是否被取消
        # 🆕 轮次管理（按用户要求：只有 AI 播完才算一轮结束）
        "turn_closed": True,            # 上一轮是否已结束（AI 播放完毕）
        "turn_closed_timeout_task": None,  # 🔧 turn_closed 超时兜底任务
        "active_message_round_id": None,  # 当前活跃的轮次 ID（未关闭前复用）
        "waiting_for_more": False,      # 是否在等待用户补充
        "waiting_task": None,           # 等待超时的 Task
        "max_wait_seconds": 5.0,        # 语义不完整时最大等待秒数
        # 🆕 防抖：避免短时间内多个 start 消息导致状态混乱
        "last_start_time": 0.0,         # 上次 start 的时间戳
        "start_debounce_ms": 200,       # 防抖间隔（毫秒）
        # 🆕 时间轴记录（12个关键时间点）
        "audio_first_frame_time": 0,    # 服务端收到首帧音频时间
        "audio_last_frame_time": 0,     # 服务端收到末帧音频时间
        "current_round_id": 0,          # 当前轮次 ID
    }

    try:
        loop = asyncio.get_event_loop()

        # ========== 检查是否是继续对话 ==========
        is_continue = False
        if conversation_id:
            try:
                from storage.impl.supabase_repository import SupabaseConversationRepository
                conv_repo = SupabaseConversationRepository()

                messages_result = conv_repo.client.table("messages").select("*").eq(
                    "conversation_id", conversation_id.strip()
                ).order("timestamp", desc=False).execute()

                if messages_result.data and len(messages_result.data) > 0:
                    is_continue = True
                    for msg in messages_result.data:
                        if msg.get("conversation_id") == conversation_id.strip():
                            conversation_history.append({
                                "role": msg["sender_role"],
                                "content": msg["content"]
                            })
                    logger.info(f"[继续对话] 加载了 {len(conversation_history)} 条历史消息")
            except Exception as e:
                logger.error(f"检查历史消息失败: {e}")

        # 发送连接成功信号
        await websocket.send_json({
            "type": "connected",
            "is_continue": is_continue or is_session_resumed,
            "pipeline": "gpt4o"
        })
        
        # 🆕 设置用户上下文（日志会自动带上 user_id）
        set_user_context(user_id or "anonymous", conversation_id)
        logger.info(f"[初始化] 连接成功, conversation_id={conversation_id}")
        
        # 🆕 记录到用户专属日志
        log_user(user_id, "info", f"[连接] 会话开始 conversation_id={conversation_id}", 
                 event="session_start", conversation_id=conversation_id)
        
        # 🆕 启动连接监控任务
        robustness_context["monitor_task"] = asyncio.create_task(connection_monitor())
        
        # 🆕 如果是断线重连恢复的会话，发送 session_resumed
        if is_session_resumed:
            await websocket.send_json({
                "type": "session_resumed",
                "message": "Session restored from cache",
                "message_count": len(conversation_history),
                "cached_duration_seconds": int(time.time() - cached_session.get("cached_at", time.time()))
            })
            logger.info(f"[会话恢复] 已发送 session_resumed, history_len={len(conversation_history)}")

        # ========== 新对话：生成初始问题（结合热点内容）==========
        if not is_continue:
            initial_question = ""
            chunk_queue = queue.Queue()
            hot_content_dict = None  # 热点内容
            use_new_user_greeting = False  # 🆕 标记是否使用新用户引导开场白

            # 🆕 新用户特殊处理：使用引导式开场白，跳过热点搜索
            if is_new_user:
                use_new_user_greeting = True
                logger.info(f"[新用户] {user_id}, 使用引导式开场白收集兴趣")
            elif CONTENT_INJECTION_ENABLED:
                # 老用户：异步获取热点内容（有超时限制，不阻塞）
                try:
                    injector = get_injector()
                    hot_content = await asyncio.wait_for(
                        injector.fetch_for_greeting_async(user_profile),
                        timeout=GREETING_HOT_CONTENT_TIMEOUT_SEC
                    )
                    if hot_content:
                        hot_content_dict = {
                            "topic": hot_content.topic,
                            "headline": hot_content.headline,
                            "detail": hot_content.detail
                        }
                        # 🆕 将开场白话题加入已搜索集合，防止后续重复搜索
                        if "searched_topics" not in hot_content_context:
                            hot_content_context["searched_topics"] = set()
                        hot_content_context["searched_topics"].add(hot_content.topic.lower())
                        # 🆕 将开场白热点也加入热点池并标记已使用
                        hot_content_context["pool"].append({
                            "topic": hot_content.topic,
                            "headline": hot_content.headline,
                            "detail": hot_content.detail,
                            "search_turn": 0,
                            "used": True  # 开场白直接使用
                        })
                        hot_content_context["inject_count"] = 1
                        hot_content_context["last_inject_turn"] = 0
                        logger.info(f"[热点轨] 🔥 开场白热点: {hot_content.topic} | 已标记为已使用")
                except asyncio.TimeoutError:
                    logger.warning("[热点轨] 开场白热点获取超时，使用普通开场白")
                except Exception as e:
                    logger.warning(f"[热点轨] 开场白热点获取失败: {e}")

            # 🆕 获取上次对话摘要用于朋友式开场（仅老用户）
            greeting_last_summary = None
            if user_id and not hot_content_dict and not is_new_user:  # 老用户且没有热点内容时使用上次对话
                try:
                    greeting_last_summary = user_repo.get_last_conversation_summary(user_id)
                    if greeting_last_summary:
                        logger.info(f"[开场白] 使用上次对话摘要: {greeting_last_summary.get('summary', '')[:50]}...")
                except Exception as e:
                    logger.warning(f"[开场白] 获取上次摘要失败: {e}")
            
            try:
                # 🆕 新用户使用引导式开场白（快速，不调用 LLM）
                if use_new_user_greeting:
                    initial_question = get_new_user_greeting()
                    logger.info(f"[新用户] 使用引导式开场白: {initial_question[:50]}...")
                    
                    # 直接发送文本
                    await websocket.send_json({
                        "type": "text_chunk",
                        "text": initial_question
                    })
                    
                    # 生成 TTS
                    try:
                        audio = pipeline.synthesize(initial_question)
                        chunk_size = 4096
                        sample_rate = pipeline.get_tts_sample_rate()
                        for i in range(0, len(audio), chunk_size):
                            await websocket.send_json({
                                "type": "audio_chunk",
                                "data": base64.b64encode(audio[i:i+chunk_size]).decode("utf-8"),
                                "format": "pcm",
                                "sample_rate": sample_rate
                            })
                        await websocket.send_json({"type": "audio_end"})
                    except Exception as tts_err:
                        logger.error(f"[新用户] TTS 失败: {tts_err}")
                    
                    chunks = []  # 跳过后续的 chunk 处理
                else:
                    # 🚀 老用户：正常生成开场白（带热点/摘要）
                    # 在执行器中运行同步生成器
                    def run_initial_question():
                        results = []
                        for chunk in pipeline.generate_initial_question_with_content(
                            user_profile,
                            hot_content_dict,
                            greeting_last_summary  # 🆕 传递上次对话摘要
                        ):
                            results.append(chunk)
                        return results
                    
                    # 设置 5 秒超时，如果超时则使用默认开场白
                    try:
                        chunks = await asyncio.wait_for(
                            loop.run_in_executor(None, run_initial_question),
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning("[初始化] 初始问题生成超时（5秒），使用默认开场白")
                        chunks = []  # 空结果，触发兜底逻辑
                
                audio_chunk_count = 0
                for chunk in chunks:
                    chunk_type = chunk.get("type")
                    
                    if chunk_type == "text_chunk":
                        initial_question += chunk.get("text", "")
                        await websocket.send_json(chunk)
                    elif chunk_type == "audio_chunk":
                        audio_chunk_count += 1
                        await websocket.send_json(chunk)
                    elif chunk_type == "audio_end":
                        logger.info(f"[初始化] 发送 {audio_chunk_count} 个音频块到前端")
                        await websocket.send_json(chunk)
                    elif chunk_type == "done":
                        initial_question = chunk.get("text", initial_question)
                        
            except Exception as e:
                logger.error(f"初始问题生成失败: {e}")
                record_anomaly("INITIAL_QUESTION_FAILED", f"初始问题生成失败: {e}")
                # 不阻断主流程，继续
                pass
            
            # 兜底：如果初始问题为空，使用固定开场白
            if not initial_question:
                initial_question = "Hi! How are you today?"
                await websocket.send_json({
                    "type": "text_chunk",
                    "text": initial_question
                })
                
                try:
                    audio = pipeline.synthesize(initial_question)
                    chunk_size = 4096
                    sample_rate = pipeline.get_tts_sample_rate()
                    for i in range(0, len(audio), chunk_size):
                        await websocket.send_json({
                            "type": "audio_chunk",
                            "data": base64.b64encode(audio[i:i+chunk_size]).decode("utf-8"),
                            "format": "pcm",
                            "sample_rate": sample_rate
                        })
                    await websocket.send_json({"type": "audio_end"})
                except Exception as tts_err:
                    logger.error(f"[初始化] 兜底 TTS 失败: {tts_err}")

            if initial_question:
                conversation_history.append({"role": "assistant", "content": initial_question})

                # 保存到数据库
                if conversation_id:
                    try:
                        from storage.impl.supabase_repository import SupabaseConversationRepository
                        conv_repo = SupabaseConversationRepository()
                        conv_repo.client.table("messages").insert({
                            "conversation_id": conversation_id,
                            "round_number": 0,
                            "sender_role": "assistant",
                            "content": initial_question,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "metadata": {
                                "is_initial": True,
                                "has_hot_content": hot_content_dict is not None,
                                "hot_topic": hot_content_dict.get("topic") if hot_content_dict else None
                            }
                        }).execute()
                    except Exception as e:
                        logger.error(f"保存初始问题失败: {e}")

                # 生成翻译
                try:
                    translation = await loop.run_in_executor(
                        None, lambda: processor.translate_only(initial_question)
                    )
                    if translation:
                        await websocket.send_json({
                            "type": "translation",
                            "text": translation
                        })
                except (WebSocketDisconnect, RuntimeError, Exception) as e:
                    # 翻译失败不影响主流程
                    logger.debug(f"[初始化] 翻译失败: {e}")

            logger.info(f"[初始化] 初始问题: {initial_question[:50]}...")

        # 发送初始化完成
        await websocket.send_json({"type": "done", "latency": {"total": 0}})

        # 🔧 turn_closed 超时兜底：防止前端未发送 assistant_played 导致状态机死锁
        TURN_CLOSED_TIMEOUT_SECONDS = 30  # 30秒未收到 assistant_played 自动关闭轮次

        async def start_turn_closed_timeout():
            """启动 turn_closed 超时兜底任务"""
            # 取消之前的超时任务
            if pipeline_context.get("turn_closed_timeout_task"):
                pipeline_context["turn_closed_timeout_task"].cancel()
                try:
                    await pipeline_context["turn_closed_timeout_task"]
                except (asyncio.CancelledError, Exception):
                    pass

            async def _timeout_fallback():
                await asyncio.sleep(TURN_CLOSED_TIMEOUT_SECONDS)
                if not pipeline_context.get("turn_closed", True):
                    logger.warning(f"[turn_closed] ⚠️ {TURN_CLOSED_TIMEOUT_SECONDS}秒未收到 assistant_played，自动关闭轮次")
                    pipeline_context["turn_closed"] = True
                    pipeline_context["active_message_round_id"] = None
                    pipeline_context["accumulated_transcript"] = ""
                    deepgram_context["accumulated_transcript"] = ""
                    pipeline_context["waiting_for_more"] = False
                    if pipeline_context.get("waiting_task"):
                        pipeline_context["waiting_task"].cancel()
                        pipeline_context["waiting_task"] = None

            pipeline_context["turn_closed_timeout_task"] = asyncio.create_task(_timeout_fallback())

        # ========== 主消息循环 ==========
        # 🆕 流式音频帧缓冲区（用于自动对话模式）
        streaming_audio_frames = []
        is_streaming = False
        frame_count = 0
        current_message_round_id = None  # 🆕 当前轮次的消息 ID
        
        # 🆕 双阈值系统状态
        speculative_stt_context = {
            "pending_transcription": None,  # 暂存的 STT 结果
            "pending_audio": None,          # 暂存的音频数据（用于评估轨）
            "is_waiting": False,            # 是否在等待长阈值确认
        }
        
        while True:
            try:
                # 🔧 修复：检查连接状态，避免断开后仍尝试接收
                if websocket.client_state.name != "CONNECTED":
                    logger.info("WebSocket 已断开，退出接收循环")
                    break
                
                message = await websocket.receive()

                if "text" in message:
                    try:
                        data = json.loads(message["text"])
                        msg_type = data.get("type")

                        # 🆕 处理前端日志上报
                        if msg_type == "frontend_log":
                            log_level = data.get("level", "info")
                            log_type = data.get("log_type", "unknown")
                            log_msg = data.get("message", "")
                            log_data = data.get("data")
                            timestamp = data.get("timestamp", int(time.time() * 1000))
                            
                            # 记录到主日志
                            if log_level == "anomaly":
                                logger.warning(f"[前端] 🚨 {log_type}: {log_msg} | data={log_data}")
                            else:
                                logger.info(f"[前端] [{log_type}] {log_msg} | data={log_data}")
                            
                            # 🆕 同时写入到 online_logs/frontend/frontend.log
                            try:
                                from datetime import timezone
                                frontend_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "online_logs", "frontend")
                                os.makedirs(frontend_log_dir, exist_ok=True)
                                frontend_log_file = os.path.join(frontend_log_dir, "frontend.log")
                                log_entry = {
                                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                                    "user_id": user_id,
                                    "conversation_id": conversation_id,
                                    "level": log_level,
                                    "type": log_type,
                                    "message": log_msg,
                                    "data": log_data,
                                    "client_timestamp_ms": timestamp
                                }
                                with open(frontend_log_file, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                            except Exception as fe:
                                logger.warning(f"[前端日志] 写入失败: {fe}")
                            continue
                        
                        # 🆕 处理前端时间轴事件
                        if msg_type == "timeline_event":
                            event_type = data.get("event_type", "unknown")
                            timestamp_ms = data.get("timestamp", int(time.time() * 1000))
                            metadata = data.get("metadata", {})
                            
                            # 🆕 暂存 client_speech_start，等 start 消息来了一起归档到新 round
                            if event_type == "client_speech_start":
                                pipeline_context["pending_client_speech_start"] = {
                                    "timestamp_ms": timestamp_ms,
                                    "metadata": metadata
                                }
                                logger.debug(f"[时间轴] 暂存 {event_type} @ {timestamp_ms}")
                                continue

                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0),
                                event_type=event_type,
                                timestamp_ms=timestamp_ms,
                                message_round_id=pipeline_context.get("active_message_round_id"),
                                source="client",
                                metadata=metadata
                            )
                            logger.debug(f"[时间轴] {event_type} @ {timestamp_ms} (来自前端)")
                            continue

                        if msg_type == "start":
                            # ========== 用户开始说话 ==========
                            # 核心逻辑：只要上一轮没播完（turn_closed=False），就是"继续同一轮"
                            # 只有 turn_closed=True 才是新一轮
                            
                            # 🆕 防抖：避免短时间内多个 start 消息导致状态混乱
                            current_time_ms = time.time() * 1000
                            last_start_time = pipeline_context.get("last_start_time", 0)
                            debounce_ms = pipeline_context.get("start_debounce_ms", 200)
                            
                            if current_time_ms - last_start_time < debounce_ms:
                                logger.warning(f"[start] ⚠️ 防抖：忽略重复 start（间隔 {current_time_ms - last_start_time:.0f}ms < {debounce_ms}ms）")
                                continue  # 跳过此消息，不处理
                            
                            pipeline_context["last_start_time"] = current_time_ms

                            # 🔧 延迟清除会话缓存：收到第一条有效 start 说明连接已稳定
                            if is_session_resumed and not _session_cache_cleared:
                                clear_session_cache(session_cache_key)
                                _session_cache_cleared = True
                                logger.info(f"[会话恢复] 连接稳定，清除会话缓存: {session_cache_key}")
                            
                            # 🆕 参考 UserGenie: 检查前端打断标记
                            is_interrupt = data.get("isInterrupt", False)
                            if is_interrupt:
                                logger.info("[start] 🛑 前端标记 isInterrupt=true，立即处理打断")
                            
                            is_continuing = not pipeline_context.get("turn_closed", True)
                            
                            # 取消任何正在等待的任务
                            if pipeline_context.get("waiting_task"):
                                logger.info("[start] 取消等待任务")
                                pipeline_context["waiting_task"].cancel()
                                pipeline_context["waiting_task"] = None
                            pipeline_context["waiting_for_more"] = False
                            
                            # 🆕 如果前端标记打断，立即停止 AI 说话（避免前几个字丢失）
                            if is_interrupt:
                                if interrupt_state.get("is_speaking"):
                                    if interrupt_state.get("interrupt_event"):
                                        interrupt_state["interrupt_event"].set()
                                    interrupt_state["is_speaking"] = False
                                    logger.info("[start] 立即停止 AI 说话（isInterrupt）")
                                
                                # 通知前端 AI 已被打断
                                await websocket.send_json({
                                    "type": "interrupted",
                                    "message": "AI speech interrupted by user (via isInterrupt flag)",
                                    "timestamp": datetime.utcnow().isoformat() + "Z"
                                })
                            
                            # 如果上一轮没结束，需要中止当前输出
                            if is_continuing:
                                logger.info("[start] turn_closed=False → 用户继续说话，进入追加模式")
                                
                                # 中止 LLM 处理
                                if pipeline_context.get("is_processing"):
                                    pipeline_context["llm_cancelled"] = True
                                    if pipeline_context.get("llm_task"):
                                        pipeline_context["llm_task"].cancel()
                                    pipeline_context["is_processing"] = False
                                
                                # 中止 AI 播放
                                if interrupt_state.get("is_speaking"):
                                    if interrupt_state.get("interrupt_event"):
                                        interrupt_state["interrupt_event"].set()
                                    interrupt_state["is_speaking"] = False
                                
                                # 通知前端：用户继续说话，复用同一条消息
                                accumulated = deepgram_context.get("accumulated_transcript", "") or pipeline_context.get("accumulated_transcript", "")
                                await websocket.send_json({
                                    "type": "user_continuing",
                                    "message": "User continuing to speak, output cancelled",
                                    "accumulated_text": accumulated,
                                    "message_round_id": pipeline_context.get("active_message_round_id"),
                                    "timestamp": datetime.utcnow().isoformat() + "Z"
                                })
                            else:
                                # 新一轮开始
                                # 🔧 修复：后端自己递增 round_id，不依赖前端 timeline_event
                                pipeline_context["current_round_id"] = pipeline_context.get("current_round_id", 0) + 1
                                logger.info(f"[start] turn_closed=True → 新一轮对话开始, round_id={pipeline_context['current_round_id']}")
                                
                                # 🆕 如果有暂存的 client_speech_start，现在归档到新 round
                                if pipeline_context.get("pending_client_speech_start"):
                                    pending = pipeline_context["pending_client_speech_start"]
                                    record_timeline_event(
                                        user_id=user_id,
                                        conversation_id=conversation_id,
                                        round_id=pipeline_context["current_round_id"],
                                        event_type="client_speech_start",
                                        timestamp_ms=pending["timestamp_ms"],
                                        source="client",
                                        metadata=pending["metadata"]
                                    )
                                    pipeline_context["pending_client_speech_start"] = None
                                    logger.debug(f"[时间轴] 归档暂存的 client_speech_start 到 round {pipeline_context['current_round_id']}")

                                # 清空累积
                                pipeline_context["accumulated_transcript"] = ""
                                deepgram_context["accumulated_transcript"] = ""
                                pipeline_context["turn_closed"] = False  # 标记新轮开始，未完成
                                # 🆕 重置本轮时间轴标记，避免后续轮次缺事件
                                pipeline_context["asr_timeline_started"] = False
                                pipeline_context["asr_timeline_ended"] = False
                                pipeline_context["tts_timeline_started"] = False
                                pipeline_context["llm_timeline_ended"] = False
                            
                            is_recording = True
                            audio_buffer = []
                            streaming_audio_frames = []
                            is_streaming = True
                            frame_count = 0
                            logger.info(f"[start] 录音开始, is_recording=True, message_round_id={current_message_round_id}, is_continuing={is_continuing}")
                            
                            # message_round_id：继续则复用，新轮则生成
                            if is_continuing and pipeline_context.get("active_message_round_id"):
                                current_message_round_id = pipeline_context["active_message_round_id"]
                            else:
                                round_number = len([m for m in conversation_history if m.get("role") == "user"]) + 1
                                current_message_round_id = f"{conversation_id}_{round_number}" if conversation_id else f"msg_{round_number}"
                                pipeline_context["active_message_round_id"] = current_message_round_id
                            
                            # 发送 recording_started 消息
                            accumulated = deepgram_context.get("accumulated_transcript", "") or pipeline_context.get("accumulated_transcript", "")
                            await websocket.send_json({
                                "type": "recording_started",
                                "message_round_id": current_message_round_id,
                                "has_accumulated": bool(accumulated),
                                "accumulated_text": accumulated if accumulated else None
                            })
                            
                            logger.info(f"[AutoMode] 开始录音/流式接收, message_round_id={current_message_round_id}, accumulated={accumulated[:30] if accumulated else 'None'}...")
                            
                            # 🆕 启动流式 ASR（支持 Deepgram / 豆包）
                            asr_available = (ASR_PROVIDER == "deepgram" and DEEPGRAM_AVAILABLE) or \
                                           (ASR_PROVIDER == "doubao" and DOUBAO_AVAILABLE)
                            if deepgram_context["is_enabled"] and asr_available:
                                try:
                                    # 🔧 检测 ASR 连接是否真正可用
                                    asr_instance = deepgram_context.get("asr")
                                    asr_truly_connected = asr_instance and asr_instance.is_connected
                                    
                                    # 🔧 关键修复：即使 is_continuing，如果 ASR 连接已断开，必须重建
                                    if is_continuing and asr_truly_connected:
                                        logger.info("[ASR] 用户继续说话，复用现有 ASR 连接")
                                        # 只重置部分状态，保留连接和累积转录
                                        deepgram_context["is_processing"] = False
                                        deepgram_context["llm_cancelled"] = False
                                    else:
                                        # 新一轮或连接已断开，需要创建新连接
                                        if is_continuing and not asr_truly_connected:
                                            logger.warning("[ASR] ⚠️ 用户继续说话但 ASR 连接已断开，重建连接")
                                        
                                        if asr_instance and asr_instance.is_connected:
                                            logger.info("[ASR] 关闭旧连接，准备新一轮")
                                            await asr_instance.stop_stream()
                                        
                                        # 重置状态（🔧 关键：保留 accumulated_transcript！等待期间用户继续说话需要累积）
                                        deepgram_context["transcript_buffer"] = ""
                                        deepgram_context["last_interim_text"] = ""
                                        deepgram_context["is_processing"] = False
                                        deepgram_context["llm_cancelled"] = False
                                        deepgram_context["is_first_transcript"] = True
                                    
                                    # 🔧 修正判断：只要没有真正可用的连接就需要创建
                                    need_new_asr = not asr_truly_connected
                                    
                                    if need_new_asr:
                                        if ASR_PROVIDER == "doubao" and DOUBAO_AVAILABLE:
                                            config = DoubaoASRConfig(language=STREAMING_ASR_LANGUAGE)
                                            # 🆕 使用热备份连接池
                                            if USE_ASR_POOL and DOUBAO_POOL_AVAILABLE:
                                                pool_config = PoolConfig(
                                                    keepalive_interval=5.0,  # 每 5 秒发送静音包
                                                )
                                                deepgram_context["asr"] = create_asr_pool(config, pool_config)
                                                deepgram_context["is_pool"] = True
                                                logger.info(f"[ASR] 🔥 使用豆包 ASR 热备份连接池, language={STREAMING_ASR_LANGUAGE}")
                                            else:
                                                deepgram_context["asr"] = create_doubao_asr(config)
                                                deepgram_context["is_pool"] = False
                                                logger.info(f"[ASR] 使用豆包 ASR, language={STREAMING_ASR_LANGUAGE}")
                                        else:
                                            config = DeepgramConfig(
                                                language=STREAMING_ASR_LANGUAGE,
                                                endpointing=300,       # 300ms 静音检测（更快响应）
                                                utterance_end_ms=2000, # 🆕 2000ms 静默后触发 utterance_end（更宽容）
                                            )
                                            deepgram_context["asr"] = create_deepgram_asr(config)
                                            logger.info(f"[ASR] 使用 Deepgram ASR, language={STREAMING_ASR_LANGUAGE}")
                                    
                                    # 🆕 定义转录回调 - 发送 asr_delta（边说边转）
                                    # 📚 学习自 UserGenie：正确处理 Deepgram 的 interim/final 结果
                                    async def on_transcript(text: str, is_final: bool):
                                        # 🛡️ 检查 WebSocket 是否仍然连接
                                        if websocket.client_state.name != "CONNECTED":
                                            logger.warning("[Deepgram] WebSocket 已断开，跳过 asr_delta")
                                            return
                                        
                                        # 🆕 判断是否为豆包ASR（豆包ASR每次返回完整文本，不是增量）
                                        is_doubao = ASR_PROVIDER == "doubao" or isinstance(deepgram_context.get("asr"), DoubaoASR) if DOUBAO_AVAILABLE else False
                                        
                                        # 📚 UserGenie 风格：正确处理 Deepgram 返回格式
                                        # - Deepgram interim: 每次返回的是【当前完整识别】，不是增量
                                        # - Deepgram final: 当前 chunk 的最终确认，需要累加到 buffer
                                        
                                        # 🔧 已移动：ASR 开始时间在收到第一帧音频时记录（见 frame_count == 1）
                                        # 这里不再重复记录 asr_start

                                        if is_final:
                                            if is_doubao:
                                                # 🔧 豆包ASR：每次返回完整文本，直接替换 buffer
                                                deepgram_context["transcript_buffer"] = text
                                            else:
                                                # ✅ Deepgram final：累加到 buffer（这是一个 chunk 的最终结果）
                                                # 📚 学习自 UserGenie：final 结果累加到 deepgramTranscript
                                                if deepgram_context["transcript_buffer"]:
                                                    deepgram_context["transcript_buffer"] += " " + text
                                                else:
                                                    deepgram_context["transcript_buffer"] = text
                                            # 清空临时结果（已确认）
                                            deepgram_context["last_interim_text"] = ""
                                            # 🆕 记录最后收到 final 的时间（用于超时兜底）
                                            deepgram_context["last_final_time"] = time.time()
                                            # 🆕 记录 ASR 结束（final 到达）
                                            record_timeline_event(
                                                user_id=user_id, conversation_id=conversation_id,
                                                round_id=pipeline_context.get("current_round_id", 0),
                                                event_type="asr_end",
                                                message_round_id=pipeline_context.get("active_message_round_id")
                                            )
                                        else:
                                            # 🆕 临时结果处理
                                            if is_doubao:
                                                # 🔧 豆包ASR：临时结果也是完整文本，直接替换 buffer
                                                deepgram_context["transcript_buffer"] = text
                                            else:
                                                # ✅ Deepgram interim：只保存，不累加到 buffer
                                                # 📚 学习自 UserGenie：interim 保存到 lastInterimText，用于兜底
                                                deepgram_context["last_interim_text"] = text
                                        
                                        # 🆕 发送 asr_delta（实时转录）给前端
                                        is_first = deepgram_context.get("is_first_transcript", False)
                                        if is_first:
                                            deepgram_context["is_first_transcript"] = False
                                        
                                        # 📚 学习自 UserGenie：正确计算 display_text
                                        # - Final: 显示累积的 buffer
                                        # - Interim: 显示 buffer + 当前 interim（interim 是完整文本，不是增量）
                                        if is_doubao:
                                            # 🆕 豆包ASR：text 已经是完整文本，直接使用
                                            display_text = text if text else deepgram_context["transcript_buffer"]
                                        else:
                                            # ✅ Deepgram：修复显示逻辑
                                            # 📚 学习自 UserGenie：
                                            # const currentText = state.deepgramTranscript + ' ' + transcript;
                                            if is_final:
                                                # Final 时，buffer 已更新，直接显示
                                                display_text = deepgram_context["transcript_buffer"]
                                            else:
                                                # Interim 时，显示 已确认buffer + 当前interim
                                                # 注意：interim 的 text 是【当前完整识别】，不是增量
                                                buffer = deepgram_context["transcript_buffer"]
                                                if buffer and text:
                                                    display_text = buffer + " " + text
                                                else:
                                                    display_text = text or buffer or ""
                                        
                                        try:
                                            await websocket.send_json({
                                                "type": "asr_delta",
                                                "text": display_text,
                                                "delta": text,
                                                "is_final": is_final,
                                                "is_first": is_first,
                                                "timestamp": datetime.utcnow().isoformat() + "Z"
                                            })
                                        except Exception as e:
                                            logger.warning(f"[Deepgram] 发送 asr_delta 失败: {e}")
                                    
                                    # 🆕 Deepgram utterance_end 回调 - 语义检测 + 累积机制 + LLM 触发
                                    async def on_utterance_end():
                                        nonlocal streaming_audio_frames, is_streaming, frame_count
                                        nonlocal current_message_round_id
                                        
                                        # 🛡️ 检查 WebSocket 是否仍然连接
                                        if websocket.client_state.name != "CONNECTED":
                                            logger.warning("[Deepgram] WebSocket 已断开，跳过 utterance_end 处理")
                                            return
                                        
                                        # 防止重复触发
                                        if deepgram_context.get("is_processing"):
                                            logger.warning("[Deepgram] utterance_end 重复触发，跳过")
                                            return
                                        
                                        # 获取当前转录结果
                                        current_transcript = deepgram_context.get("transcript_buffer", "")
                                        
                                        # 兜底：如果最终结果为空但有临时结果
                                        if not current_transcript.strip():
                                            last_interim = deepgram_context.get("last_interim_text", "")
                                            if last_interim.strip():
                                                logger.info(f"[Deepgram] 使用临时结果兜底: {last_interim[:50]}...")
                                                current_transcript = last_interim
                                        
                                        # 🆕 判断是否为豆包ASR
                                        is_doubao = ASR_PROVIDER == "doubao" or isinstance(deepgram_context.get("asr"), DoubaoASR) if DOUBAO_AVAILABLE else False
                                        
                                        # 合并累积的转录（跨多次 utterance_end）
                                        accumulated = deepgram_context.get("accumulated_transcript", "")
                                        if is_doubao:
                                            # 🔧 豆包ASR：每次 text 已经是完整转录（包含所有 utterances），直接使用
                                            # 不需要累积！豆包 ASR 会自己返回完整内容
                                            full_transcript = current_transcript
                                        else:
                                            # Deepgram：正常累积（增量文本需要拼接）
                                            if accumulated:
                                                full_transcript = accumulated + " " + current_transcript
                                            else:
                                                full_transcript = current_transcript
                                        full_transcript = full_transcript.strip()
                                        
                                        logger.info(f"[Deepgram] utterance_end: current='{current_transcript[:30]}...', accumulated='{accumulated[:30] if accumulated else ''}', full='{full_transcript[:50]}...'")
                                        
                                        if not full_transcript:
                                            logger.warning("[Deepgram] 转录为空，跳过")
                                            return
                                        
                                        # ========== 🆕 防重复发送逻辑（参考 UserGenie） ==========
                                        import time as time_module
                                        current_time = time_module.time()
                                        last_text = deepgram_context.get("last_utterance_text", "")
                                        last_time = deepgram_context.get("last_utterance_time", 0)
                                        
                                        # 如果文本相同且间隔 < 1秒，跳过发送
                                        if full_transcript == last_text and (current_time - last_time) < 1.0:
                                            logger.debug(f"[Deepgram] 防重复：文本相同且间隔<1s，跳过 utterance_end")
                                            return
                                        
                                        # 更新记录
                                        deepgram_context["last_utterance_text"] = full_transcript
                                        deepgram_context["last_utterance_time"] = current_time
                                        
                                        # ========== 新规则：on_utterance_end 只做通知，不触发处理 ==========
                                        # 处理由前端 stop_audio 触发，这里只更新状态和通知前端
                                        
                                        # 更新累积转录
                                        deepgram_context["accumulated_transcript"] = full_transcript
                                        pipeline_context["accumulated_transcript"] = full_transcript
                                        
                                        # 通知前端当前转录状态（仅通知，不触发处理）
                                        try:
                                            await websocket.send_json({
                                                "type": "utterance_end",
                                                "text": full_transcript,
                                                "message_round_id": current_message_round_id,
                                                "timestamp": datetime.utcnow().isoformat() + "Z"
                                            })
                                        except Exception as e:
                                            logger.warning(f"[Deepgram] 发送 utterance_end 失败: {e}")
                                        
                                        # 清空当前 buffer，准备接收新内容
                                        deepgram_context["transcript_buffer"] = ""
                                        deepgram_context["last_interim_text"] = ""
                                        
                                        logger.info("[Deepgram] utterance_end 完成（仅通知，等待 stop_audio 触发处理）")
                                    
                                    # 🆕 参考 UserGenie: 重连回调，通知前端 ASR 重连状态
                                    async def on_reconnect(attempt: int, success: bool):
                                        """ASR 重连回调 - 通知前端重连状态"""
                                        try:
                                            if websocket.client_state.name != "CONNECTED":
                                                return
                                            
                                            if success:
                                                # 重连成功
                                                await websocket.send_json({
                                                    "type": "asr_reconnected",
                                                    "message": "ASR connection restored",
                                                    "timestamp": datetime.utcnow().isoformat() + "Z"
                                                })
                                                logger.info("[ASR] 重连成功，已通知前端")
                                            else:
                                                # 正在重连
                                                # 🆕 保存当前转录到 context（避免丢失）
                                                preserved = deepgram_context.get("transcript_buffer", "")
                                                if preserved:
                                                    deepgram_context["preserved_transcript"] = preserved
                                                    logger.info(f"[ASR] 保存转录到 context: '{preserved[:30]}...'")
                                                
                                                await websocket.send_json({
                                                    "type": "asr_reconnecting",
                                                    "message": f"ASR connection lost, reconnecting (attempt {attempt})...",
                                                    "attempt": attempt,
                                                    "timestamp": datetime.utcnow().isoformat() + "Z"
                                                })
                                                logger.info(f"[ASR] 正在重连 (attempt {attempt})，已通知前端")
                                        except Exception as e:
                                            logger.warning(f"[ASR] 发送重连通知失败: {e}")
                                    
                                    # 🆕 热切换回调（仅用于 Pool 模式）
                                    async def on_hot_switch(switch_count: int):
                                        """ASR 热切换回调 - 通知前端已无缝切换"""
                                        try:
                                            if websocket.client_state.name != "CONNECTED":
                                                return
                                            await websocket.send_json({
                                                "type": "asr_hot_switch",
                                                "message": f"ASR hot standby activated (switch #{switch_count})",
                                                "switch_count": switch_count,
                                                "timestamp": datetime.utcnow().isoformat() + "Z"
                                            })
                                            logger.info(f"[ASR Pool] 🔥 热切换完成 (第 {switch_count} 次)，已通知前端")
                                        except Exception as e:
                                            logger.warning(f"[ASR Pool] 发送热切换通知失败: {e}")
                                    
                                    # 启动 ASR 连接（只有需要新连接时）
                                    if need_new_asr:
                                        if deepgram_context.get("is_pool"):
                                            # 🆕 Pool 模式：使用 start() 方法
                                            await deepgram_context["asr"].start(
                                                on_transcript=on_transcript,
                                                on_utterance_end=on_utterance_end,
                                                on_error=None,
                                                on_switch=on_hot_switch  # 🆕 热切换回调
                                            )
                                            logger.info("[ASR Pool] 🔥 热备份连接池已启动（含重连回调）")
                                        else:
                                            await deepgram_context["asr"].start_stream(
                                                on_transcript=on_transcript,
                                                on_utterance_end=on_utterance_end,
                                                on_reconnect=on_reconnect  # 🆕 添加重连回调
                                            )
                                        logger.info("[Deepgram] 流式 ASR 已启动（含重连回调）")
                                    else:
                                        logger.info("[Deepgram] 复用现有 ASR 连接，继续接收音频")
                                    
                                    # 🆕 Flush buffered audio (发送暂存的预录音)
                                    if deepgram_context.get("audio_buffer"):
                                        buffered_count = len(deepgram_context["audio_buffer"])
                                        logger.info(f"[Deepgram] 连接建立，发送暂存的 {buffered_count} 帧音频")
                                        pvad_fn = deepgram_context.get("pvad_filter", lambda x: x)
                                        for buffered_frame in deepgram_context["audio_buffer"]:
                                            filtered = pvad_fn(buffered_frame)
                                            if filtered:
                                                await deepgram_context["asr"].send_audio(filtered)
                                        deepgram_context["audio_buffer"] = []
                                    
                                except Exception as e:
                                    logger.error(f"[Deepgram] 启动失败: {e}，回退到批量 ASR")
                                    record_anomaly("DEEPGRAM_START_FAILED", f"Deepgram 启动失败: {e}")
                                    deepgram_context["is_enabled"] = False
                            
                        elif msg_type == "audio_meta":
                            audio_format = data.get("format", "wav")
                            
                        elif msg_type == "audio_frame":
                            # 🔧 向后兼容：JSON 格式的音频帧（新版前端已改用二进制发送）
                            if is_streaming:
                                frame_data = data.get("data", [])
                                if frame_data:
                                    # 将 Int16 数组转换为 bytes
                                    import struct
                                    pcm_bytes = struct.pack(f'<{len(frame_data)}h', *frame_data)
                                    streaming_audio_frames.append(pcm_bytes)
                                    frame_count += 1
                                    
                                    # 🆕 记录首帧时间（时间轴关键点3）
                                    if frame_count == 1:
                                        first_frame_time = int(time.time() * 1000)
                                        pipeline_context["audio_first_frame_time"] = first_frame_time
                                        record_timeline_event(
                                            user_id=user_id,
                                            conversation_id=conversation_id,
                                            round_id=pipeline_context.get("current_round_id", 0),
                                            event_type="server_audio_first",
                                            timestamp_ms=first_frame_time,
                                            message_round_id=pipeline_context.get("active_message_round_id")
                                        )
                                        # 🔧 修复：ASR 开始时间 = 收到第一帧音频时（而不是收到首个转录时）
                                        if not pipeline_context.get("asr_timeline_started"):
                                            pipeline_context["asr_timeline_started"] = True
                                            record_timeline_event(
                                                user_id=user_id,
                                                conversation_id=conversation_id,
                                                round_id=pipeline_context.get("current_round_id", 0),
                                                event_type="asr_start",
                                                timestamp_ms=first_frame_time,
                                                message_round_id=pipeline_context.get("active_message_round_id")
                                            )
                                    
                                    # 🆕 发送音频到 Deepgram（如果启用流式 ASR）
                                    if deepgram_context["is_enabled"]:
                                        # 检查是否已连接
                                        if deepgram_context["asr"] and deepgram_context["asr"].is_connected:
                                            pvad_fn = deepgram_context.get("pvad_filter", lambda x: x)
                                            filtered = pvad_fn(pcm_bytes)
                                            if filtered:
                                                await deepgram_context["asr"].send_audio(filtered)
                                        else:
                                            # 未连接时暂存到缓冲（pVAD 过滤在 flush 时执行）
                                            deepgram_context["audio_buffer"].append(pcm_bytes)
                                            # 日志限频
                                            if len(deepgram_context["audio_buffer"]) % 10 == 1:
                                                logger.info(f"[Deepgram] 未连接，暂存音频帧 #{len(deepgram_context['audio_buffer'])}")
                                    
                                    # 每 30 帧记录一次（约 1 秒）
                                    if frame_count % 30 == 0:
                                        total_bytes = sum(len(f) for f in streaming_audio_frames)
                                        logger.info(f"[流式音频] 已接收 {frame_count} 帧, 总大小: {total_bytes} bytes (当前帧: {len(pcm_bytes)} bytes)")
                                        
                        elif msg_type == "speculative_stt":
                            # 🆕 双阈值系统：短阈值触发，预启动 STT
                            logger.info(f"[双阈值] 收到 speculative_stt, 共 {frame_count} 帧")
                            
                            if streaming_audio_frames and is_streaming:
                                # 将流式帧合并为完整音频
                                audio_data_bytes = b''.join(streaming_audio_frames)
                                wav_audio = create_wav_from_pcm(audio_data_bytes, 16000)
                                
                                logger.info(f"[双阈值] 开始预启动 STT: {len(wav_audio)} bytes")
                                
                                # 暂存音频数据
                                speculative_stt_context["pending_audio"] = wav_audio
                                speculative_stt_context["is_waiting"] = True
                                
                                # 异步执行 STT（不阻塞）
                                async def run_speculative_stt():
                                    try:
                                        asr_prompt = "This is an English speaking practice conversation."
                                        if conversation_history:
                                            last_ai_msg = next((m for m in reversed(conversation_history) if m.get("role") == "assistant"), None)
                                            if last_ai_msg:
                                                prev_content = last_ai_msg.get("content", "")[:100].replace("\n", " ")
                                                asr_prompt += f" Previous AI said: '{prev_content}'. User replies:"
                                        
                                        transcription = await loop.run_in_executor(
                                            None,
                                            lambda: pipeline.transcribe(wav_audio, "wav", prompt=asr_prompt)
                                        )
                                        
                                        # 暂存 STT 结果
                                        speculative_stt_context["pending_transcription"] = transcription
                                        logger.info(f"[双阈值] STT 完成: {transcription[:50]}...")
                                        
                                        # 发送转录结果（让用户看到）
                                        await websocket.send_json({
                                            "type": "transcription",
                                            "text": transcription,
                                            "is_speculative": True,  # 标记为预启动结果
                                            "timestamp": datetime.utcnow().isoformat() + "Z"
                                        })
                                        
                                    except Exception as e:
                                        logger.error(f"[双阈值] 预启动 STT 失败: {e}")
                                        speculative_stt_context["pending_transcription"] = None
                                
                                asyncio.create_task(run_speculative_stt())
                            
                        elif msg_type == "confirm_end":
                            # 🆕 双阈值系统：长阈值触发，确认用户说完
                            logger.info(f"[双阈值] 收到 confirm_end")
                            
                            if speculative_stt_context["is_waiting"]:
                                speculative_stt_context["is_waiting"] = False
                                pipeline_context["is_processing"] = True  # 🔧 标记正在处理，防止 stop_audio 误清理
                                
                                # 检查是否有暂存的 STT 结果
                                pending_transcription = speculative_stt_context["pending_transcription"]
                                pending_audio = speculative_stt_context["pending_audio"]
                                
                                if pending_transcription and pending_audio:
                                    logger.info(f"[双阈值] 使用预启动 STT 结果，触发 LLM")
                                    
                                    # 使用暂存的数据处理（跳过 STT，直接进入 LLM）
                                    audio_buffer = [pending_audio]
                                    audio_format = "wav"
                                    
                                    # 🔧 使用已分配的 message_round_id（与 recording_started 一致）
                                    current_message_round_id = pipeline_context.get("active_message_round_id")
                                    if not current_message_round_id:
                                        round_number = len([m for m in conversation_history if m.get("role") == "user"]) + 1
                                        current_message_round_id = f"{conversation_id}_{round_number}" if conversation_id else f"msg_{round_number}"
                                    logger.info(f"[双阈值] 使用 message_round_id: {current_message_round_id}")
                                    
                                    # 🆕 从热点池中选择最佳热点
                                    current_turn = hot_content_context.get("turn_count", 0)
                                    pending_content = select_best_hot_content(
                                        hot_content_context, conversation_history, current_turn
                                    )
                                    
                                    await process_audio_stream_with_transcription(
                                        websocket=websocket,
                                        pipeline=pipeline,
                                        processor=processor,
                                        transcription=pending_transcription,
                                        audio_data=pending_audio,
                                        audio_format=audio_format,
                                        conversation_history=conversation_history,
                                        user_profile=user_profile,
                                        user_id=user_id,
                                        user_repo=user_repo,
                                        conversation_id=conversation_id,
                                        eval_context=eval_context,
                                        pending_hot_content=pending_content,
                                        hot_content_context=hot_content_context,
                                        memory_context=memory_context,
                                        message_round_id=current_message_round_id,
                                        interrupt_state=interrupt_state  # 🆕 传入打断状态
                                    )
                                    
                                    if pending_content:
                                        current_turn = hot_content_context.get("turn_count", 0)
                                        mark_hot_content_used(hot_content_context, pending_content, current_turn)
                                else:
                                    logger.warning("[双阈值] confirm_end 但没有暂存的 STT 结果")
                                
                                # 清理状态
                                speculative_stt_context["pending_transcription"] = None
                                speculative_stt_context["pending_audio"] = None
                            
                            # 重置录音状态
                            streaming_audio_frames = []
                            is_streaming = False
                            frame_count = 0
                            audio_buffer = []
                            is_recording = False
                            current_message_round_id = None
                            
                        elif msg_type == "cancel_stt":
                            # 🆕 双阈值系统：用户继续说话，取消预启动
                            logger.info(f"[双阈值] 收到 cancel_stt, 用户继续说话")
                            
                            # 丢弃暂存的 STT 结果
                            speculative_stt_context["pending_transcription"] = None
                            speculative_stt_context["pending_audio"] = None
                            speculative_stt_context["is_waiting"] = False
                            
                            # 注意：不重置 streaming_audio_frames，因为用户还在说话
                            # 新的音频帧会继续追加到 streaming_audio_frames
                            
                        elif msg_type == "stop_audio":
                            # ========== 前端静默触发 - 主入口 ==========
                            # 按新规则：stop_audio 是"用户可能说完了"的主信号
                            
                            # 🆕 记录末帧时间（时间轴关键点4）
                            last_frame_time = int(time.time() * 1000)
                            pipeline_context["audio_last_frame_time"] = last_frame_time
                            record_timeline_event(
                                user_id=user_id,
                                conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0),
                                event_type="server_audio_last",
                                timestamp_ms=last_frame_time,
                                message_round_id=pipeline_context.get("active_message_round_id"),
                                metadata={"frame_count": frame_count}
                            )
                            
                            # 🆕 计算音频能量，判断是否静音
                            total_audio_bytes = sum(len(f) for f in streaming_audio_frames)
                            audio_energy = 0.0
                            if streaming_audio_frames:
                                try:
                                    import struct
                                    all_audio = b''.join(streaming_audio_frames)
                                    if len(all_audio) >= 2:
                                        samples = struct.unpack(f"<{len(all_audio)//2}h", all_audio)
                                        audio_energy = (sum(s*s for s in samples) / len(samples)) ** 0.5 if samples else 0
                                except Exception as e:
                                    logger.warning(f"[stop_audio] 计算音频能量失败: {e}")
                            
                            # 🆕 详细日志：帧数、时长、能量
                            audio_duration_ms = (total_audio_bytes / 2) / 16  # 16kHz, 16-bit = 32 bytes/ms
                            is_likely_silent = audio_energy < 500  # 能量阈值，低于此值可能是静音
                            logger.info(f"[stop_audio] 收到前端静默信号, 共 {frame_count} 帧, {audio_duration_ms:.0f}ms, 能量={audio_energy:.0f} {'⚠️可能静音' if is_likely_silent else '✓有声音'}")
                            
                            # 如果正在处理中，跳过（防止重复触发）
                            if pipeline_context.get("is_processing"):
                                logger.info("[stop_audio] 正在处理中，跳过")
                                continue
                            
                            # 获取 Deepgram 流式转录结果（🔧 不立即关闭连接！）
                            deepgram_transcription = ""
                            deepgram_failed = False
                            asr_still_connected = False  # 标记 ASR 是否仍连接
                            
                            if deepgram_context["is_enabled"] and deepgram_context["asr"]:
                                if deepgram_context["asr"].is_connected:
                                    # 🔧 关键修复：检查 ASR 是否还在处理中
                                    # 使用 ASR 的 is_processing 属性（基于 definite 字段），不用固定时间
                                    asr = deepgram_context["asr"]
                                    
                                    if asr.is_processing:
                                        # ASR 还在处理，等待它完成（最多等 10 次，每次 100ms）
                                        logger.info(f"[stop_audio] ASR 还在处理中，等待完成...")
                                        for _ in range(10):
                                            await asyncio.sleep(0.1)
                                            if not asr.is_processing:
                                                break
                                        if asr.is_processing:
                                            logger.warning(f"[stop_audio] ASR 处理超时，使用当前结果")
                                    
                                    # P0 修复：豆包需先发 EOS（stop_stream）再取最终结果，否则拿到的是流式中间结果
                                    is_doubao_asr = ASR_PROVIDER == "doubao" and DOUBAO_AVAILABLE
                                    if is_doubao_asr:
                                        deepgram_transcription = await asr.stop_stream()
                                        asr_still_connected = False  # 连接已关闭，后续不再调用 stop_stream
                                        logger.info(f"[stop_audio] 豆包 ASR 已结束流并取回最终转录: '{deepgram_transcription[:50] if deepgram_transcription else '(空)'}...'")
                                    else:
                                        deepgram_transcription = asr.get_full_transcript()
                                        asr_still_connected = True
                                        logger.info(f"[stop_audio] 获取转录（连接保持）: '{deepgram_transcription[:50] if deepgram_transcription else '(空)'}...'")
                                else:
                                    # 连接已关闭，使用缓冲区中的结果
                                    deepgram_transcription = deepgram_context.get("transcript_buffer", "")
                                    logger.info(f"[stop_audio] 连接已关闭，使用缓冲: '{deepgram_transcription[:50]}...'")
                                
                                # 兜底：如果最终结果为空但有临时结果
                                if not deepgram_transcription.strip():
                                    # 1. 尝试临时结果
                                    last_interim = deepgram_context.get("last_interim_text", "")
                                    if last_interim.strip():
                                        logger.info(f"[stop_audio] 使用临时结果兜底: '{last_interim[:50]}...'")
                                        deepgram_transcription = last_interim
                                    
                                    # 2. 尝试累积结果（如果是已经 final 的情况）
                                    if not deepgram_transcription.strip():
                                        accumulated = deepgram_context.get("accumulated_transcript", "")
                                        if accumulated.strip():
                                            logger.info(f"[stop_audio] 使用累积结果兜底: '{accumulated[:50]}...'")
                                            deepgram_transcription = accumulated

                                # 如果仍为空，短暂等待 ASR 推送临时结果
                                if not deepgram_transcription.strip():
                                    await asyncio.sleep(0.3)
                                    deepgram_transcription = deepgram_context.get("transcript_buffer", "") or deepgram_context.get("last_interim_text", "")
                                    if deepgram_transcription.strip():
                                        logger.info(f"[stop_audio] 延迟兜底结果: '{deepgram_transcription[:50]}...'")
                                
                                # Deepgram 仍无结果，标记回退到批量 ASR
                                if not deepgram_transcription.strip():
                                    deepgram_failed = True
                                    logger.info("[stop_audio] Deepgram 暂无结果，回退到批量 ASR")
                                
                                deepgram_context["last_interim_text"] = ""
                            
                            # 如果 Deepgram 有转录结果，检查语义完整性后触发 LLM
                            if deepgram_transcription and deepgram_transcription.strip():
                                # 🆕 确保 ASR 时间轴成对记录（流式无 final 时兜底）
                                if not pipeline_context.get("asr_timeline_started"):
                                    pipeline_context["asr_timeline_started"] = True
                                    record_timeline_event(
                                        user_id=user_id, conversation_id=conversation_id,
                                        round_id=pipeline_context.get("current_round_id", 0),
                                        event_type="asr_start",
                                        message_round_id=pipeline_context.get("active_message_round_id"),
                                        timestamp_ms=pipeline_context.get("audio_first_frame_time") or int(time.time() * 1000)
                                    )
                                if not pipeline_context.get("asr_timeline_ended"):
                                    pipeline_context["asr_timeline_ended"] = True
                                    record_timeline_event(
                                        user_id=user_id, conversation_id=conversation_id,
                                        round_id=pipeline_context.get("current_round_id", 0),
                                        event_type="asr_end",
                                        message_round_id=pipeline_context.get("active_message_round_id")
                                    )
                                # 🆕 语义完整性检查（兜底路径）- 使用已有的 semantic_checker
                                semantic_checker = get_semantic_checker()
                                
                                # 🆕 记录语义检测时间（包含 Timeline 事件）
                                semantic_start = time.time()
                                record_timeline_event(
                                    user_id=user_id, conversation_id=conversation_id,
                                    round_id=pipeline_context.get("current_round_id", 0),
                                    event_type="semantic_start",
                                    message_round_id=pipeline_context.get("active_message_round_id")
                                )
                                
                                is_complete, confidence, reason = True, 1.0, "default"
                                try:
                                    is_complete, confidence, reason = await semantic_checker.check_async(deepgram_transcription)
                                except Exception as e:
                                    logger.warning(f"[语义检测] 异常，默认视为完整: {e}")
                                    is_complete, confidence, reason = True, 1.0, "error_fallback"

                                semantic_end = time.time()
                                record_timeline_event(
                                    user_id=user_id, conversation_id=conversation_id,
                                    round_id=pipeline_context.get("current_round_id", 0),
                                    event_type="semantic_end",
                                    message_round_id=pipeline_context.get("active_message_round_id")
                                )
                                
                                semantic_latency_ms = int((semantic_end - semantic_start) * 1000)
                                
                                # 存储到 pipeline_context 供后续 metrics 使用
                                pipeline_context["semantic_start_time"] = semantic_start
                                pipeline_context["semantic_end_time"] = semantic_end
                                
                                logger.info(f"[stop_audio] 语义检测: 完整={is_complete}, 置信度={confidence:.2f}, 原因={reason}, 耗时={semantic_latency_ms}ms")
                                
                                # 语义不完整时：累积文本 + 启动最大等待计时器
                                # 🔧 放宽条件：只有明确不完整（置信度 >= 0.7）才等待，否则直接处理
                                if not is_complete and confidence >= 0.7:
                                    logger.info(f"[stop_audio] 语义不完整，进入等待模式，最大等待 {pipeline_context['max_wait_seconds']}s")
                                    
                                    # 累积文本
                                    # 🔧 豆包ASR：每次返回完整文本，直接使用，不累积
                                    is_doubao = ASR_PROVIDER == "doubao" or (DOUBAO_AVAILABLE and isinstance(deepgram_context.get("asr"), DoubaoASR))
                                    if is_doubao:
                                        pipeline_context["accumulated_transcript"] = deepgram_transcription.strip()
                                    else:
                                        # Deepgram：增量文本需要累积
                                        accumulated = pipeline_context.get("accumulated_transcript", "")
                                        if deepgram_transcription.strip().startswith(accumulated.strip()):
                                            pipeline_context["accumulated_transcript"] = deepgram_transcription.strip()
                                        else:
                                            pipeline_context["accumulated_transcript"] = (accumulated + " " + deepgram_transcription).strip()
                                    deepgram_context["accumulated_transcript"] = pipeline_context["accumulated_transcript"]
                                    
                                    pipeline_context["waiting_for_more"] = True
                                    
                                    # 通知前端
                                    await websocket.send_json({
                                        "type": "waiting_for_more",
                                        "text": pipeline_context["accumulated_transcript"],
                                        "confidence": confidence,
                                        "reason": reason,
                                        "max_wait": pipeline_context["max_wait_seconds"],
                                        "message_round_id": current_message_round_id,
                                        "timestamp": datetime.utcnow().isoformat() + "Z"
                                    })
                                    
                                    # 启动最大等待计时器（如果用户不补充，强制处理）
                                    if pipeline_context.get("waiting_task"):
                                        pipeline_context["waiting_task"].cancel()
                                    
                                    # 捕获当前上下文
                                    wait_transcription = pipeline_context["accumulated_transcript"]
                                    wait_round_id = current_message_round_id
                                    wait_audio = b''.join(streaming_audio_frames) if streaming_audio_frames else b''
                                    
                                    async def force_process_after_wait():
                                        logger.info(f"[等待任务] 开始等待 {pipeline_context['max_wait_seconds']} 秒...")
                                        try:
                                            await asyncio.sleep(pipeline_context["max_wait_seconds"])
                                            # 检查是否还在等待（用户没有继续说话）
                                            waiting_flag = pipeline_context.get("waiting_for_more")
                                            logger.info(f"[等待任务] 等待结束, waiting_for_more={waiting_flag}")
                                            if not waiting_flag:
                                                logger.info("[等待任务] waiting_for_more=False，跳过处理")
                                                return
                                            
                                            logger.info(f"[等待任务] 超时，强制处理: '{wait_transcription[:40]}...'")
                                            pipeline_context["waiting_for_more"] = False
                                            pipeline_context["is_processing"] = True
                                            
                                            # 🔧 先通知前端取消等待状态（关键修复）
                                            await websocket.send_json({
                                                "type": "waiting_cancelled",
                                                "reason": "timeout",
                                                "message_round_id": wait_round_id,
                                                "timestamp": datetime.utcnow().isoformat() + "Z"
                                            })
                                            logger.info("[等待任务] 已通知前端取消等待")
                                            
                                            # 合并音频
                                            wav_audio = create_wav_from_pcm(wait_audio, 16000) if wait_audio else b''
                                            
                                            # 发送转录
                                            logger.info("[等待任务] 发送最终转录...")
                                            await websocket.send_json({
                                                "type": "transcription",
                                                "text": wait_transcription,
                                                "message_round_id": wait_round_id,
                                                "is_final": True,
                                                "source": "timeout_force",
                                                "timestamp": datetime.utcnow().isoformat() + "Z"
                                            })
                                            
                                            # 触发 LLM
                                            logger.info("[等待任务] 触发 LLM 处理...")
                                            await process_audio_stream_with_transcription(
                                                websocket=websocket,
                                                pipeline=pipeline,
                                                processor=processor,
                                                transcription=wait_transcription,
                                                audio_data=wav_audio,
                                                audio_format="wav",
                                                conversation_history=conversation_history,
                                                user_profile=user_profile,
                                                user_id=user_id,
                                                user_repo=user_repo,
                                                conversation_id=conversation_id,
                                                eval_context=eval_context,
                                                pending_hot_content=hot_content_context.get("pending"),
                                                hot_content_context=hot_content_context,
                                                memory_context=memory_context,
                                                pipeline_context=pipeline_context,
                                                message_round_id=wait_round_id,
                                                interrupt_state=interrupt_state
                                            )
                                            logger.info("[等待任务] ✅ LLM 处理完成")
                                            pipeline_context["is_processing"] = False
                                        except asyncio.CancelledError:
                                            logger.info("[等待任务] 被取消（用户继续说话）")
                                        except Exception as e:
                                            logger.error(f"[等待任务] 出错: {e}", exc_info=True)
                                            pipeline_context["is_processing"] = False
                                    
                                    logger.info("[stop_audio] 创建等待任务...")
                                    pipeline_context["waiting_task"] = asyncio.create_task(force_process_after_wait())
                                    logger.info("[stop_audio] 等待任务已创建")
                                    
                                    # 重置流状态，但保留累积
                                    streaming_audio_frames = []
                                    is_streaming = False
                                    frame_count = 0
                                    continue  # 不立即触发 LLM
                                
                                # 🔧 修复：如果有累积的文本，使用累积的完整文本（用户说 A → 停顿 → 说 C 时发 A+C）
                                accumulated_text = pipeline_context.get("accumulated_transcript", "")
                                # 🆕 判断是否为豆包ASR
                                is_doubao = ASR_PROVIDER == "doubao" or (DOUBAO_AVAILABLE and isinstance(deepgram_context.get("asr"), DoubaoASR))
                                
                                if is_doubao:
                                    # 🔧 豆包ASR：若有累积（如 waiting_for_more 后用户继续说），合并后再发；否则用当前转录
                                    new_segment = deepgram_transcription.strip()
                                    if accumulated_text.strip() and new_segment and new_segment not in accumulated_text:
                                        final_transcription = (accumulated_text.strip() + " " + new_segment).strip()
                                        logger.info(f"[stop_audio] 🔧 豆包ASR 累积+新段: '{accumulated_text[:25]}...' + '{new_segment[:25]}...' = '{final_transcription[:50]}...'")
                                    else:
                                        final_transcription = new_segment or accumulated_text.strip()
                                        if final_transcription:
                                            logger.info(f"[stop_audio] 🔧 豆包ASR 直接使用: '{final_transcription[:50]}...'")
                                elif accumulated_text.strip():
                                    # Deepgram：增量累积逻辑
                                    if deepgram_transcription.strip() and deepgram_transcription.strip() not in accumulated_text:
                                        final_transcription = (accumulated_text + " " + deepgram_transcription).strip()
                                    else:
                                        final_transcription = accumulated_text.strip()
                                    logger.info(f"[stop_audio] 🔗 Deepgram累积: '{accumulated_text[:30]}...' + '{deepgram_transcription[:20]}...' = '{final_transcription[:50]}...'")
                                else:
                                    final_transcription = deepgram_transcription
                                
                                logger.info(f"[stop_audio] 🚀 语义完整，触发 LLM: '{final_transcription[:50]}...'")
                                
                                # 🔧 语义完整时才关闭 ASR 连接
                                if asr_still_connected and deepgram_context["asr"] and deepgram_context["asr"].is_connected:
                                    logger.info("[stop_audio] 语义完整，关闭 ASR 连接")
                                    await deepgram_context["asr"].stop_stream()
                                
                                # 清空累积（已经使用完毕）
                                pipeline_context["accumulated_transcript"] = ""
                                deepgram_context["accumulated_transcript"] = ""
                                pipeline_context["waiting_for_more"] = False
                                
                                # 将流式帧合并为 WAV（用于评估轨）
                                wav_audio = None
                                if streaming_audio_frames:
                                    audio_data_bytes = b''.join(streaming_audio_frames)
                                    wav_audio = create_wav_from_pcm(audio_data_bytes, 16000)
                                    logger.info(f"[stop_audio] 音频合并完成: {len(wav_audio)} bytes")
                                
                                # 发送最终转录给前端
                                await websocket.send_json({
                                    "type": "transcription",
                                    "text": final_transcription,
                                    "message_round_id": current_message_round_id,
                                    "is_final": True,
                                    "source": "stop_audio_fallback",
                                    "timestamp": datetime.utcnow().isoformat() + "Z"
                                })
                                
                                # 🆕 从热点池中选择最佳热点
                                current_turn = hot_content_context.get("turn_count", 0)
                                pending_content = select_best_hot_content(
                                    hot_content_context, conversation_history, current_turn
                                )
                                
                                try:
                                    await process_audio_stream_with_transcription(
                                        websocket=websocket,
                                        pipeline=pipeline,
                                        processor=processor,
                                        transcription=final_transcription,
                                        audio_data=wav_audio or b'',
                                        audio_format="wav",
                                        conversation_history=conversation_history,
                                        user_profile=user_profile,
                                        user_id=user_id,
                                        user_repo=user_repo,
                                        conversation_id=conversation_id,
                                        eval_context=eval_context,
                                        pending_hot_content=pending_content,
                                        hot_content_context=hot_content_context,
                                        memory_context=memory_context,
                                        pipeline_context=pipeline_context,
                                        message_round_id=current_message_round_id,
                                        interrupt_state=interrupt_state
                                    )
                                    logger.info("[stop_audio] ✅ LLM 处理完成")
                                except Exception as e:
                                    logger.error(f"[stop_audio] ❌ LLM 处理失败: {e}", exc_info=True)
                                    record_anomaly("LLM_PROCESS_FAILED", f"LLM 处理失败: {e}")
                                    await websocket.send_json({"type": "error", "message": "LLM 处理失败"})
                                
                                if pending_content:
                                    current_turn = hot_content_context.get("turn_count", 0)
                                    mark_hot_content_used(hot_content_context, pending_content, current_turn)
                            else:
                                # 流式无结果时：有音频且本轮在流式 → 会走下面批量 ASR 兜底，不先发 recording_cancelled
                                will_try_batch_asr = (
                                    (not deepgram_context["is_enabled"] or deepgram_failed)
                                    or (not (deepgram_transcription and deepgram_transcription.strip()))
                                ) and streaming_audio_frames and is_streaming
                                
                                if will_try_batch_asr:
                                    logger.info("[stop_audio] 流式 ASR 无结果，将尝试批量 ASR 兜底")
                                else:
                                    logger.info("[stop_audio] 转录为空，通知前端清理空消息")
                                    if asr_still_connected and deepgram_context["asr"] and deepgram_context["asr"].is_connected:
                                        logger.info("[stop_audio] 空转录，关闭 ASR 连接")
                                        await deepgram_context["asr"].stop_stream()
                                    await websocket.send_json({
                                        "type": "recording_cancelled",
                                        "message_round_id": current_message_round_id,
                                        "reason": "empty_transcription"
                                    })
                            
                            # 流式无有效结果且有音频时，尝试批量 ASR 兜底（条件与上面一致，避免重复变量）
                            should_try_batch_asr = (
                                (not deepgram_context["is_enabled"] or deepgram_failed)
                                or (not (deepgram_transcription and deepgram_transcription.strip()))
                            ) and streaming_audio_frames and is_streaming
                            if should_try_batch_asr:
                                logger.info(f"[stop_audio] 流式 ASR 无结果，尝试批量 ASR 兜底 (enabled={deepgram_context['is_enabled']})")
                                
                                audio_data_bytes = b''.join(streaming_audio_frames)
                                wav_audio = create_wav_from_pcm(audio_data_bytes, 16000)
                                
                                # Step 1: GPT-4o Whisper 转录
                                await websocket.send_json({"type": "processing", "stage": "asr"})
                                
                                asr_prompt = "This is an English speaking practice conversation."
                                if conversation_history:
                                    last_ai_msg = next((m for m in reversed(conversation_history) if m.get("role") == "assistant"), None)
                                    if last_ai_msg:
                                        prev_content = last_ai_msg.get("content", "")[:100].replace("\n", " ")
                                        asr_prompt += f" Previous AI said: '{prev_content}'. User replies:"
                                
                                transcription = await loop.run_in_executor(
                                    None,
                                    lambda: pipeline.transcribe(wav_audio, "wav", prompt=asr_prompt)
                                )
                                logger.info(f"[stop_audio] ASR 完成: {transcription[:50]}...")
                                
                                # 发送转录结果给前端
                                await websocket.send_json({
                                    "type": "transcription",
                                    "text": transcription,
                                    "message_round_id": current_message_round_id,
                                    "is_final": True,
                                    "source": "gpt4o_whisper",
                                    "timestamp": datetime.utcnow().isoformat() + "Z"
                                })
                                
                                # 🆕 检查空转录
                                if not transcription or not transcription.strip():
                                    logger.warning("[stop_audio] ASR 返回空文本，跳过处理")
                                    # 🔧 修复：发送 recording_cancelled 让前端删除空消息并重置状态
                                    logger.info(f"[stop_audio] 发送 recording_cancelled, message_round_id={current_message_round_id}")
                                    if asr_still_connected and deepgram_context["asr"] and deepgram_context["asr"].is_connected:
                                        logger.info("[stop_audio] 空转录，关闭 ASR 连接")
                                        await deepgram_context["asr"].stop_stream()
                                    await websocket.send_json({
                                        "type": "recording_cancelled",
                                        "message_round_id": current_message_round_id,
                                        "reason": "empty_transcription"
                                    })
                                    # 重置状态
                                    streaming_audio_frames = []
                                    is_streaming = False
                                    frame_count = 0
                                    is_recording = False
                                    current_message_round_id = None
                                    continue
                                
                                # Step 2: 语义完整性检测
                                # 使用顶部已导入的 get_semantic_checker（不要在这里重复 import）
                                semantic_checker = get_semantic_checker()
                                
                                # 🆕 记录语义检测时间
                                semantic_start = time.time()
                                is_complete, confidence, reason = True, 1.0, "default"
                                try:
                                    is_complete, confidence, reason = await semantic_checker.check_async(transcription)
                                except Exception as e:
                                    logger.warning(f"[语义检测] 异常，默认视为完整: {e}")
                                    is_complete, confidence, reason = True, 1.0, "error_fallback"
                                semantic_end = time.time()
                                semantic_latency_ms = int((semantic_end - semantic_start) * 1000)
                                
                                # 存储到 pipeline_context 供后续 metrics 使用
                                pipeline_context["semantic_start_time"] = semantic_start
                                pipeline_context["semantic_end_time"] = semantic_end
                                
                                logger.info(f"[stop_audio] 语义检测: complete={is_complete}, confidence={confidence:.2f}, reason={reason}, 耗时={semantic_latency_ms}ms")
                                
                                # Step 3: 根据语义完整性设置处理策略（乐观执行）
                                tts_delay = 0
                                if not is_complete and confidence >= 0.7:
                                    # 语义不完整，等待用户继续说话
                                    pipeline_context["llm_status"] = "TENTATIVE"
                                    
                                    # 累积当前文本
                                    # 🔧 豆包ASR：直接使用，不累积
                                    is_doubao = ASR_PROVIDER == "doubao" or (DOUBAO_AVAILABLE and isinstance(deepgram_context.get("asr"), DoubaoASR))
                                    if is_doubao:
                                        pipeline_context["accumulated_transcript"] = transcription.strip()
                                    else:
                                        # Deepgram：增量累积
                                        accumulated = pipeline_context.get("accumulated_transcript", "")
                                        if transcription.strip().startswith(accumulated.strip()) and len(transcription) > len(accumulated):
                                             pipeline_context["accumulated_transcript"] = transcription.strip()
                                        else:
                                             pipeline_context["accumulated_transcript"] = (accumulated + " " + transcription).strip()
                                         
                                    logger.info(f"[stop_audio] TENTATIVE 模式。累积: {pipeline_context['accumulated_transcript'][:50]}... 等待 5 秒")
                                    
                                    # 🆕 通知前端：进入等待模式
                                    await websocket.send_json({
                                        "type": "waiting_for_more",
                                        "text": pipeline_context["accumulated_transcript"],
                                        "confidence": confidence,
                                        "reason": reason,
                                        "tts_delay": 5.0,
                                        "timestamp": datetime.utcnow().isoformat() + "Z"
                                    })
                                    
                                    # 🆕 启动后台等待任务，避免阻塞主循环
                                    if pipeline_context.get("tentative_task"):
                                        pipeline_context["tentative_task"].cancel()
                                        
                                    # 捕获当前需要的上下文变量
                                    current_full_transcription = pipeline_context["accumulated_transcript"]
                                    current_wav_audio = wav_audio # 注意：这里只保存了最后一段音频，如果需要完整音频可能需要累积，但对 LLM 来说文本才是关键
                                    
                                    async def delayed_process():
                                        try:
                                            await asyncio.sleep(5.0)
                                            if pipeline_context.get("user_speaking_again"):
                                                logger.info("[TENTATIVE] 任务被标记为取消（用户继续说话）")
                                                return
                                                
                                            logger.info("[TENTATIVE] 5 秒等待结束，触发 FINAL 处理")
                                            pipeline_context["llm_status"] = "FINAL"
                                            pipeline_context["accumulated_transcript"] = "" # 清空累积
                                            
                                            pipeline_context["is_processing"] = True
                                            # 🆕 从热点池中选择最佳热点
                                            current_turn = hot_content_context.get("turn_count", 0)
                                            pending_content = select_best_hot_content(
                                                hot_content_context, conversation_history, current_turn
                                            )
                                            
                                            await process_audio_stream_with_transcription(
                                                websocket=websocket,
                                                pipeline=pipeline,
                                                processor=processor,
                                                transcription=current_full_transcription,
                                                audio_data=current_wav_audio,
                                                audio_format="wav",
                                                conversation_history=conversation_history,
                                                user_profile=user_profile,
                                                user_id=user_id,
                                                user_repo=user_repo,
                                                conversation_id=conversation_id,
                                                eval_context=eval_context,
                                                pending_hot_content=pending_content,
                                                hot_content_context=hot_content_context,
                                                memory_context=memory_context,
                                                message_round_id=current_message_round_id,
                                                interrupt_state=interrupt_state,
                                                pipeline_context=pipeline_context,
                                                tts_delay=0
                                            )
                                            
                                            pipeline_context["is_processing"] = False
                                            pipeline_context["llm_status"] = "IDLE"
                                            if pending_content:
                                                current_turn = hot_content_context.get("turn_count", 0)
                                                mark_hot_content_used(hot_content_context, pending_content, current_turn)
                                                
                                        except asyncio.CancelledError:
                                            logger.info("[TENTATIVE] 等待任务被取消")
                                        except Exception as e:
                                            logger.error(f"[TENTATIVE] 延迟处理出错: {e}", exc_info=True)
                                            pipeline_context["is_processing"] = False
                                    
                                    pipeline_context["tentative_task"] = asyncio.create_task(delayed_process())
                                    
                                    # 立即返回，不阻塞
                                    continue
                                else:
                                    # 语义完整，正常处理
                                    pipeline_context["llm_status"] = "FINAL"
                                    tts_delay = 0
                                    # 清空之前的累积
                                    pipeline_context["accumulated_transcript"] = "" 
                                    logger.info(f"[stop_audio] FINAL 模式。")

                                # Step 4: 触发 LLM 处理
                                if pipeline_context["llm_status"] == "TENTATIVE":
                                    full_transcription = pipeline_context["accumulated_transcript"]
                                else:
                                    full_transcription = transcription

                                pipeline_context["is_processing"] = True
                                
                                # 🆕 从热点池中选择最佳热点
                                current_turn = hot_content_context.get("turn_count", 0)
                                pending_content = select_best_hot_content(
                                    hot_content_context, conversation_history, current_turn
                                )
                                
                                await process_audio_stream_with_transcription(
                                    websocket=websocket,
                                    pipeline=pipeline,
                                    processor=processor,
                                    transcription=full_transcription,
                                    audio_data=wav_audio,
                                    audio_format="wav",
                                    conversation_history=conversation_history,
                                    user_profile=user_profile,
                                    user_id=user_id,
                                    user_repo=user_repo,
                                    conversation_id=conversation_id,
                                    eval_context=eval_context,
                                    pending_hot_content=pending_content,
                                    hot_content_context=hot_content_context,
                                    memory_context=memory_context,
                                    message_round_id=current_message_round_id,
                                    interrupt_state=interrupt_state,
                                    pipeline_context=pipeline_context,  # 🆕 传入 pipeline_context
                                    tts_delay=tts_delay  # 🆕 传入 TTS 延迟
                                )
                                
                                pipeline_context["is_processing"] = False
                                pipeline_context["llm_status"] = "IDLE"  # 重置状态
                                
                                if pending_content:
                                    current_turn = hot_content_context.get("turn_count", 0)
                                    mark_hot_content_used(hot_content_context, pending_content, current_turn)
                            
                            # 重置状态
                            streaming_audio_frames = []
                            is_streaming = False
                            frame_count = 0
                            audio_buffer = []
                            is_recording = False
                            current_message_round_id = None
                            pipeline_context["llm_cancelled"] = False
                            
                        elif msg_type == "audio_end":
                            # 原有的批量音频处理（手动模式）
                            if audio_buffer and is_recording:
                                # 🆕 从热点池中选择最佳热点
                                current_turn = hot_content_context.get("turn_count", 0)
                                pending_content = select_best_hot_content(
                                    hot_content_context, conversation_history, current_turn
                                )

                                await process_audio_stream(
                                    websocket=websocket,
                                    pipeline=pipeline,
                                    processor=processor,
                                    audio_buffer=audio_buffer,
                                    audio_format=audio_format,
                                    conversation_history=conversation_history,
                                    user_profile=user_profile,
                                    user_id=user_id,
                                    user_repo=user_repo,
                                    conversation_id=conversation_id,
                                    eval_context=eval_context,
                                    pending_hot_content=pending_content,
                                    hot_content_context=hot_content_context,
                                    memory_context=memory_context,
                                    message_round_id=current_message_round_id,
                                    interrupt_state=interrupt_state,  # 🆕 传入打断状态
                                    pipeline_context=pipeline_context  # 🆕 传入 Pipeline 上下文
                                )

                                # 🆕 标记热点已使用
                                if pending_content:
                                    current_turn = hot_content_context.get("turn_count", 0)
                                    mark_hot_content_used(hot_content_context, pending_content, current_turn)
                                    logger.info("[热点轨] 热点内容已使用，已标记")

                                audio_buffer = []
                                is_recording = False
                                current_message_round_id = None  # 🆕 重置
                        elif msg_type == "set_voice_style":
                            # 🆕 设置语音风格
                            style_id = data.get("style_id", "friendly")
                            success = pipeline.set_voice_style(style_id)
                            await websocket.send_json({
                                "type": "voice_style_set",
                                "success": success,
                                "style_id": style_id
                            })
                            logger.info(f"[语音风格] 已设置为: {style_id}")
                        
                        elif msg_type == "assistant_played":
                            # ========== 前端通知：AI 语音已播放完毕 ==========
                            # 这是"一轮结束"的唯一标志（用户规则）
                            played_round_id = data.get("message_round_id")
                            logger.info(f"[assistant_played] 收到播放完成信号, round_id={played_round_id}")
                            
                            # 🆕 完成时间轴记录（一轮对话结束）
                            round_id = pipeline_context.get("current_round_id", 0)
                            timeline_data = finalize_round_timeline(user_id, conversation_id, round_id)
                            if timeline_data:
                                latencies = timeline_data.get("latencies", {})
                                logger.info(f"[时间轴] ✅ 轮次 {round_id} 完成 | "
                                           f"用户感知={latencies.get('user_perceived_ms', 0)}ms, "
                                           f"ASR={latencies.get('asr_ms', 0)}ms, "
                                           f"LLM={latencies.get('llm_total_ms', 0)}ms, "
                                           f"TTS={latencies.get('tts_total_ms', 0)}ms")
                            
                            # 标记轮次结束
                            pipeline_context["turn_closed"] = True
                            pipeline_context["active_message_round_id"] = None
                            pipeline_context["accumulated_transcript"] = ""
                            deepgram_context["accumulated_transcript"] = ""
                            pipeline_context["waiting_for_more"] = False

                            # 🔧 取消 turn_closed 超时兜底任务（正常收到了 assistant_played）
                            if pipeline_context.get("turn_closed_timeout_task"):
                                pipeline_context["turn_closed_timeout_task"].cancel()
                                pipeline_context["turn_closed_timeout_task"] = None

                            # 取消等待任务（如果有）
                            if pipeline_context.get("waiting_task"):
                                pipeline_context["waiting_task"].cancel()
                                pipeline_context["waiting_task"] = None
                            
                            # 通知前端确认
                            await websocket.send_json({
                                "type": "turn_closed",
                                "message_round_id": played_round_id,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            })
                            logger.info(f"[assistant_played] ✅ 轮次已关闭，下次用户开口将是新一轮")
                        
                        elif msg_type == "interrupt":
                            # 🆕 用户打断 AI 说话
                            if interrupt_state and interrupt_state.get("is_speaking"):
                                # 触发中断事件
                                if interrupt_state.get("interrupt_event"):
                                    interrupt_state["interrupt_event"].set()
                                interrupt_state["is_speaking"] = False
                                logger.info("[打断] 用户触发打断，已发送中断信号")
                                await websocket.send_json({
                                    "type": "interrupted",
                                    "message": "AI 响应已中断"
                                })
                            else:
                                logger.debug("[打断] 收到打断信号但 AI 未在说话")
                                await websocket.send_json({
                                    "type": "interrupted",
                                    "message": "AI 未在说话"
                                })
                            
                        elif msg_type == "ping":
                            # 🆕 心跳响应 + 活动时间更新
                            robustness_context["last_activity_time"] = time.time()
                            robustness_context["last_ping_time"] = time.time()
                            robustness_context["inactivity_warning_sent"] = False
                            await websocket.send_json({
                                "type": "pong",
                                "timestamp": int(time.time() * 1000),
                                "server_time": datetime.utcnow().isoformat() + "Z"
                            })
                        
                        elif msg_type == "user_perceived_latency":
                            # 🆕 前端上报用户感知延迟（VAD静默→TTS首块播放）
                            latency_ms = data.get("latency_ms", 0)
                            message_round_id = data.get("message_round_id", "")
                            vad_silence_time = data.get("vad_silence_time", 0)
                            first_audio_time = data.get("first_audio_time", 0)
                            
                            logger.info(f"📊 [用户感知延迟-前端] {latency_ms}ms (VAD→TTS首块), round_id={message_round_id}")
                            
                            # 记录到 metrics
                            record_latency("user_perceived", latency_ms)
                            
                            # 可选：保存到数据库或发送到监控系统
                            # 这里只记录日志，后续可扩展
                            
                        elif msg_type == "close":
                            break
                    except json.JSONDecodeError:
                        pass

                elif "bytes" in message:
                    # 🔧 修复：二进制音频帧同时支持流式 ASR（前端改为二进制发送后走这条路径）
                    pcm_bytes = message["bytes"]
                    audio_size = len(pcm_bytes)
                    if is_recording:
                        audio_buffer.append(pcm_bytes)

                        # 流式模式：同步追加到 streaming_audio_frames 并发送到 ASR
                        if is_streaming:
                            streaming_audio_frames.append(pcm_bytes)
                            frame_count += 1

                            # 记录首帧时间（时间轴关键点3）
                            if frame_count == 1:
                                first_frame_time = int(time.time() * 1000)
                                pipeline_context["audio_first_frame_time"] = first_frame_time
                                record_timeline_event(
                                    user_id=user_id,
                                    conversation_id=conversation_id,
                                    round_id=pipeline_context.get("current_round_id", 0),
                                    event_type="server_audio_first",
                                    timestamp_ms=first_frame_time,
                                    message_round_id=pipeline_context.get("active_message_round_id")
                                )
                                if not pipeline_context.get("asr_timeline_started"):
                                    pipeline_context["asr_timeline_started"] = True
                                    record_timeline_event(
                                        user_id=user_id,
                                        conversation_id=conversation_id,
                                        round_id=pipeline_context.get("current_round_id", 0),
                                        event_type="asr_start",
                                        timestamp_ms=first_frame_time,
                                        message_round_id=pipeline_context.get("active_message_round_id")
                                    )

                            # 发送音频到流式 ASR
                            if deepgram_context["is_enabled"]:
                                if deepgram_context["asr"] and deepgram_context["asr"].is_connected:
                                    pvad_fn = deepgram_context.get("pvad_filter", lambda x: x)
                                    filtered = pvad_fn(pcm_bytes)
                                    if filtered:
                                        await deepgram_context["asr"].send_audio(filtered)
                                else:
                                    deepgram_context["audio_buffer"].append(pcm_bytes)
                                    if len(deepgram_context["audio_buffer"]) % 10 == 1:
                                        logger.info(f"[Deepgram] ASR 未连接，缓冲音频 #{len(deepgram_context['audio_buffer'])}")

                        # 日志限频
                        if len(audio_buffer) % 30 == 1:
                            total_bytes = sum(len(chunk) for chunk in audio_buffer)
                            logger.info(f"[音频接收] 已接收 {len(audio_buffer)} 帧, 总大小: {total_bytes} bytes (当前帧: {audio_size} bytes)")
                    else:
                        logger.warning(f"[音频接收] 收到音频数据但未在录音状态, 大小: {audio_size} bytes, is_recording={is_recording}")

            except WebSocketDisconnect:
                logger.info("WebSocket 断开")
                # 🆕 记录连接关闭（监控指标）
                connection_closed(user_id)
                # 🆕 缓存会话状态（支持断线重连）
                if conversation_history and len(conversation_history) > 0:
                    cache_session_state(session_cache_key, {
                        "conversation_history": conversation_history,
                        "user_profile": user_profile,
                        "accumulated_transcript": pipeline_context.get("accumulated_transcript", ""),
                    })
                break
            except Exception as e:
                # 🔧 修复：接收消息时的异常也要退出循环
                logger.error(f"接收消息错误: {e}", exc_info=True)
                connection_closed(user_id)  # 🔧 修复：确保调用 connection_closed
                break

    except Exception as e:
        logger.error(f"WebSocket 错误: {e}", exc_info=True)
        # 🔧 修复：异常时也调用 connection_closed
        connection_closed(user_id)
        # 🆕 异常时也缓存会话状态
        if conversation_history and len(conversation_history) > 0:
            cache_session_state(session_cache_key, {
                "conversation_history": conversation_history,
                "user_profile": user_profile,
                "accumulated_transcript": pipeline_context.get("accumulated_transcript", ""),
            })

    finally:
        # 🔧 修复：双重保险，确保连接计数正确
        try:
            connection_closed(user_id)
        except Exception:
            pass  # 忽略计数错误，避免影响清理流程
        
        # 🆕 停止连接监控
        robustness_context["is_monitoring"] = False
        if robustness_context.get("monitor_task"):
            robustness_context["monitor_task"].cancel()
            try:
                await robustness_context["monitor_task"]
            except asyncio.CancelledError:
                pass
            logger.info("[连接监控] 已停止")
        
        # 🆕 记录完整会话统计
        session_duration = time.time() - robustness_context["session_start_time"]
        anomaly_count = len(robustness_context.get("anomaly_events", []))
        
        # 计算会话指标
        user_messages = len([m for m in conversation_history if m.get("role") == "user"])
        ai_messages = len([m for m in conversation_history if m.get("role") == "assistant"])
        total_turns = user_messages  # 用户发言次数 = 对话轮次
        
        # 记录会话结束指标
        conversation_ended(conversation_id)
        
        # 构建会话汇总
        session_summary = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "duration_seconds": round(session_duration, 1),
            "total_turns": total_turns,
            "user_messages": user_messages,
            "ai_messages": ai_messages,
            "anomaly_count": anomaly_count,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # 记录到日志（结构化格式，方便检索）
        logger.info(f"[会话结束] 📊 汇总: conversation_id={conversation_id}, "
                    f"时长={session_duration:.0f}s, 轮次={total_turns}, "
                    f"用户消息={user_messages}, AI消息={ai_messages}, 异常={anomaly_count}")
        
        # 🆕 记录到用户专属日志
        try:
            log_user(user_id, "info", f"[断开] 会话结束 conversation_id={conversation_id}, 时长={session_duration:.0f}s, 轮次={total_turns}",
                     event="session_end", conversation_id=conversation_id, 
                     duration_seconds=round(session_duration, 1), total_turns=total_turns,
                     user_messages=user_messages, ai_messages=ai_messages)
        except Exception as e:
            logger.error(f"[用户日志] 记录断开失败: {e}")
        
        # 记录到 metrics
        increment("completed_conversations")
        log_perf(user_id or "anonymous", "session_duration", session_duration * 1000)  # 转为毫秒
        
        # 保存会话汇总到数据库
        if conversation_id:
            try:
                from storage.impl.supabase_repository import SupabaseConversationRepository
                conv_repo = SupabaseConversationRepository()
                conv_repo.client.table("conversations").update({
                    "ended_at": datetime.utcnow().isoformat() + "Z",
                    "state": "completed",
                    "metadata": {
                        "duration_seconds": round(session_duration, 1),
                        "total_turns": total_turns,
                        "anomaly_count": anomaly_count
                    }
                }).eq("conversation_id", conversation_id).execute()
                logger.info(f"[会话结束] 已保存到数据库: {conversation_id}")
            except Exception as e:
                logger.error(f"[会话结束] 保存数据库失败: {e}")
        
        # 🆕 清理 Deepgram 资源
        if deepgram_context.get("asr"):
            try:
                if deepgram_context["asr"].is_connected:
                    await deepgram_context["asr"].stop_stream()
                logger.info("[Deepgram] 清理完成")
            except Exception as e:
                logger.warning(f"[Deepgram] 清理失败: {e}")
        
        # 🆕 确保所有未完成的 timeline 都被记录（防止 assistant_played 未发送的情况）
        try:
            current_round = pipeline_context.get("current_round_id", 0)
            for round_id in range(1, current_round + 1):
                timeline_data = finalize_round_timeline(user_id, conversation_id, round_id)
                if timeline_data:
                    logger.info(f"[会话结束] 📊 补充记录 timeline round {round_id}")
        except Exception as e:
            logger.warning(f"[会话结束] timeline 记录失败: {e}")
        
        # 保存用户画像
        if user_id and user_profile:
            try:
                db_profile = user_repo.get(user_id)
                if db_profile:
                    from models.user import CEFRLevel, InterestTag

                    if 'overall_score' in user_profile:
                        db_profile.overall_score = user_profile['overall_score']
                    if 'strengths' in user_profile:
                        db_profile.strengths = user_profile['strengths']
                    if 'weaknesses' in user_profile:
                        db_profile.weaknesses = user_profile['weaknesses']

                    if 'cefr_level' in user_profile:
                        level_str = user_profile['cefr_level']
                        if isinstance(level_str, str):
                            level_str = level_str.split('/')[0].strip()
                            try:
                                db_profile.cefr_level = CEFRLevel(level_str)
                            except ValueError:
                                pass

                    if 'interests' in user_profile and user_profile['interests']:
                        interest_strings = user_profile['interests']
                        existing_tags = []
                        for interest in db_profile.interests:
                            if isinstance(interest, InterestTag):
                                existing_tags.extend(interest.tags)
                            elif isinstance(interest, str):
                                existing_tags.append(interest)

                        new_tags = [t for t in interest_strings if isinstance(t, str) and t not in existing_tags]
                        if new_tags:
                            db_profile.interests.append(InterestTag(category="general", tags=new_tags))

                    user_repo.save(db_profile)
                    logger.info(f"用户画像已保存: {user_id}")
                    
                    # 🆕 使缓存失效，下次加载时获取最新数据
                    cache = get_user_cache()
                    cache.invalidate(user_id)
                    # 如果是新用户首次保存，标记为已注册
                    if user_profile.get('is_new_user'):
                        cache.mark_as_registered(user_id)
                        user_profile['is_new_user'] = False  # 更新本地状态
            except Exception as e:
                logger.error(f"保存用户画像失败: {e}")
        
        # 🆕 保存对话摘要（跨对话持久化）
        if user_id and memory and len(memory.messages) > 0:
            try:
                # 生成最终摘要
                final_summary = memory.session_summary
                
                # 如果没有摘要但有对话历史，生成一个
                if not final_summary and memory.messages:
                    messages_for_summary = memory.get_messages_for_api()
                    if messages_for_summary:
                        final_summary = await generate_conversation_summary(messages_for_summary, "")
                
                if final_summary:
                    # 保存到数据库
                    user_repo.save_last_conversation_summary(
                        user_id,
                        final_summary,
                        memory.discussed_topics
                    )
                    logger.info(f"[跨对话摘要] 已保存: {user_id}, 长度={len(final_summary)}")
            except Exception as e:
                logger.error(f"[跨对话摘要] 保存失败: {e}")


async def process_audio_stream(
    websocket: WebSocket,
    pipeline: GPT4oPipeline,
    processor: UnifiedProcessor,
    audio_buffer: list,
    audio_format: str,
    conversation_history: list,
    user_profile: dict,
    user_id: Optional[str],
    user_repo,
    conversation_id: Optional[str],
    eval_context: dict,
    pending_hot_content: Optional[Dict[str, Any]] = None,
    hot_content_context: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
    message_round_id: Optional[str] = None,  # 🆕 预先计算的消息 ID（确保前后端一致）
    interrupt_state: Optional[Dict[str, Any]] = None,  # 🆕 打断状态（支持用户打断 AI）
    pipeline_context: Optional[Dict[str, Any]] = None  # 🆕 Pipeline 上下文（轮次管理）
):
    """
    处理用户音频 - GPT-4o 三段链路 + Qwen-Omni 评估轨 + 热点注入 + 记忆管理

    流程：
    1. 交互轨（GPT-4o）：ASR → LLM → TTS（流式）
       - 🆕 使用记忆上下文增强 LLM 理解
       - 🆕 如果有 pending_hot_content，注入到回复中
    2. 评估轨（Qwen-Omni）：异步评估（不阻塞）
       - 🆕 检测用户兴趣点，触发热点搜索（结果存入 hot_content_context["pending"]）
       - 🆕 提取关键信息更新用户画像
    3. 记忆管理：
       - 添加消息到短期记忆
       - Token-Aware 自动截断
       - 触发摘要生成（如需要）
    """
    timings = {}
    total_start = time.time()
    
    # 🆕 初始化打断事件
    if interrupt_state is not None:
        interrupt_state["interrupt_event"] = asyncio.Event()
        interrupt_state["is_speaking"] = False

    try:
        audio_data = b''.join(audio_buffer)
        if not audio_data:
            await websocket.send_json({"type": "error", "message": "音频为空"})
            return

        min_audio_size = 10 * 1024
        if len(audio_data) < min_audio_size:
            logger.warning(f"[处理] 音频太小: {len(audio_data)} bytes")
            await websocket.send_json({"type": "error", "message": "音频太短，请重新录音"})
            return

        logger.info(f"[处理] 音频大小: {len(audio_data)} bytes")
        await websocket.send_json({"type": "processing", "stage": "asr"})

        loop = asyncio.get_event_loop()

        # 🆕 使用传入的 message_round_id（如果有），否则重新计算（兼容旧模式）
        round_number = len([m for m in conversation_history if m.get("role") == "user"]) + 1
        if not message_round_id:
            message_round_id = f"{conversation_id}_{round_number}" if conversation_id else f"msg_{round_number}"
        
        logger.info(f"[处理] message_round_id={message_round_id}")

        # ========== 评估轨（三阶段并行评估）==========
        # 架构：
        #   阶段1: Qwen-Omni 语音评估（发音/韵律）  ─┐
        #   阶段2: GPT 文本评估（语法/词汇/句式）   ─┼─→ 阶段3: GPT 综合评分
        #
        # 注意：阶段2需要转录结果，所以实际流程是：
        #   交互轨 ASR 完成 → 并行启动阶段1+2 → 阶段3汇总

        eval_semaphore = eval_context["semaphore"]
        eval_tasks = eval_context["tasks"]
        eval_context["counter"][0] += 1
        current_order = eval_context["counter"][0]

        # 用于在评估轨和交互轨之间共享转录结果
        transcription_ready = asyncio.Event()
        shared_transcription = {"text": ""}

        async def run_evaluation_async():
            """评估轨 - 三阶段并行评估"""
            eval_start = time.time()
            logger.info(f"[评估轨] 启动三阶段评估, message_round_id={message_round_id}")

            # 评分节奏控制：非指定轮次跳过评估
            if EVALUATION_CADENCE_TURNS > 1 and (current_order % EVALUATION_CADENCE_TURNS) != 0:
                await websocket.send_json({
                    "type": "evaluation_skipped",
                    "message_round_id": message_round_id,
                    "order": current_order,
                    "reason": "cadence"
                })
                return

            try:
                await asyncio.wait_for(eval_semaphore.acquire(), timeout=0.1)
            except asyncio.TimeoutError:
                logger.warning(f"[评估轨] 队列已满，跳过")
                await websocket.send_json({
                    "type": "evaluation_skipped",
                    "message_round_id": message_round_id,
                    "order": current_order,
                    "reason": "queue_full"
                })
                return

            try:
                # ========== 等待转录结果（来自交互轨 ASR）==========
                try:
                    await asyncio.wait_for(transcription_ready.wait(), timeout=30)
                except asyncio.TimeoutError:
                    logger.warning("[评估轨] 等待转录超时，跳过")
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "transcription_timeout"
                    })
                    return

                transcription_text = shared_transcription["text"]
                if not transcription_text or transcription_text.strip() == "":
                    logger.warning("[评估轨] 转录为空，跳过")
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "empty_transcription"
                    })
                    return

                # 🔴 调试：打印 conversation_history 中的用户消息数量
                user_msgs_in_history = [
                    msg.get("content", "")[:30] 
                    for msg in conversation_history 
                    if msg.get("role") == "user"
                ]
                logger.info(f"[评估轨] 历史用户消息数: {len(user_msgs_in_history)}, 内容: {user_msgs_in_history[-3:] if user_msgs_in_history else []}")
                
                aggregated_transcription = _aggregate_recent_user_texts(
                    conversation_history,
                    transcription_text.strip(),
                    EVALUATION_AGGREGATE_TURNS
                )
                if not aggregated_transcription:
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "empty_transcription"
                    })
                    return
                logger.info(f"[评估轨] 聚合转录 (max={EVALUATION_AGGREGATE_TURNS}轮): {aggregated_transcription[:80]}...")

                # ========== 使用 EvaluationTrack 执行三阶段评估 ==========
                # EvaluationTrack 内部已封装：
                # - 阶段1: Qwen-Omni 语音评估（发音/韵律）
                # - 阶段2: GPT 文本评估（语法/词汇/句式）
                # - 阶段3: GPT 综合评分
                evaluation_track = get_evaluation_track()

                eval_result = await evaluation_track.evaluate(
                    transcription=aggregated_transcription,
                    audio_data=audio_data,
                    audio_format=audio_format,
                    user_profile=user_profile
                )

                eval_time = time.time() - eval_start
                logger.info(f"[评估轨] 三阶段评估完成, 耗时: {eval_time:.2f}s")

                # 转换为字典格式（与原评估轨完全兼容）
                final_evaluation = eval_result.to_dict()

                # 更新用户画像
                if final_evaluation.get("overall_score") is not None:
                    from services.unified_processor import ProcessingResult
                    eval_result = ProcessingResult(
                        transcription=transcription_text,
                        evaluation=final_evaluation,
                        interests=[],
                        ai_feedback="",
                        next_question="",
                        full_response=""
                    )
                    UserProfileUpdater.update(user_profile, eval_result)

                    # 更新对话评分
                    if conversation_id:
                        try:
                            from storage.impl.supabase_repository import SupabaseConversationRepository
                            conv_repo = SupabaseConversationRepository()
                            score = final_evaluation.get("overall_score", 0)
                            calculated_level = UserProfileUpdater._score_to_cefr(score)
                            conv_repo.client.table("conversations").update({
                                "cefr_level": calculated_level,
                                "overall_score": score
                            }).eq("conversation_id", conversation_id).execute()
                        except Exception as e:
                            logger.warning(f"[评估轨] 更新对话评分失败: {e}")

                # 根据分数计算 CEFR 等级（确保一致性）
                score = final_evaluation.get("overall_score", 0)
                calculated_level = UserProfileUpdater._score_to_cefr(score)
                final_evaluation["cefr_level"] = calculated_level

                # 发送评估结果
                await websocket.send_json({
                    "type": "evaluation",
                    "data": final_evaluation,
                    "message_round_id": message_round_id,
                    "order": current_order,
                    "latency": round(eval_time, 2)
                })

                logger.info(f"[评估轨] 三阶段完成, 总耗时: {eval_time:.2f}s, 分数: {score}, 等级: {calculated_level}")

                # 🆕 保存评估轨返回的 interests 到 memory（话题检测已移到交互轨，每轮执行）
                detected_interests = final_evaluation.get("interests", [])
                if detected_interests and memory:
                    for topic in detected_interests:
                        if topic and topic not in memory.discussed_topics:
                            memory.discussed_topics.append(topic)
                    logger.info(f"[Memory] 从评估轨更新 discussed_topics: {memory.discussed_topics}")

            except asyncio.TimeoutError:
                logger.warning(f"[评估轨] 超时")
                await websocket.send_json({
                    "type": "evaluation_skipped",
                    "message_round_id": message_round_id,
                    "order": current_order,
                    "reason": "timeout"
                })
            except Exception as e:
                logger.error(f"[评估轨] 失败: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "evaluation_skipped",
                    "message_round_id": message_round_id,
                    "order": current_order,
                    "reason": "error"
                })
            finally:
                eval_semaphore.release()
                if message_round_id in eval_tasks:
                    del eval_tasks[message_round_id]

        # 启动评估轨（异步，不阻塞交互轨）
        eval_task = asyncio.create_task(run_evaluation_async())
        eval_tasks[message_round_id] = eval_task

        # ========== 交互轨（GPT-4o 三段链路）==========
        chunk_queue = queue.Queue()
        # 注意：这里不再预先判断是否注入，而是在 ASR 后根据用户当前发言动态判断

        def run_interaction():
            """在线程中运行 GPT-4o 三段链路"""
            try:
                # 🆕 创建性能指标追踪器
                metrics = PerformanceMetrics()
                metrics.user_stop_speaking_time = time.time()
                
                # Step 1: ASR 转录（无论是否注入都需要先转录）
                # 🆕 添加 ASR prompt 提高识别准确率（英语口语练习场景）
                asr_prompt = "This is an English speaking practice conversation. The user is practicing English conversation skills."
                
                # 🚀 增强 ASR Context: 将上一轮 AI 回复加入 prompt，防止幻觉
                if conversation_history:
                    last_ai_msg = next((m for m in reversed(conversation_history) if m.get("role") == "assistant"), None)
                    if last_ai_msg:
                        prev_content = last_ai_msg.get("content", "")[:100].replace("\n", " ")
                        asr_prompt += f" Previous AI said: '{prev_content}'. User replies:"
                
                # 🔧 修复：ASR 开始时间应使用收到第一帧音频的时间，而不是当前时间
                # 如果 pipeline_context 中有 audio_first_frame_time，使用它；否则使用当前时间
                asr_start_timestamp_ms = pipeline_context.get("audio_first_frame_time") if pipeline_context else None
                if asr_start_timestamp_ms:
                    metrics.asr_start_time = asr_start_timestamp_ms / 1000.0
                    chunk_queue.put(("timeline", {"event_type": "asr_start", "timestamp_ms": asr_start_timestamp_ms}))
                else:
                    # 兜底：如果没有 audio_first_frame_time，使用当前时间（但这种情况不应该发生）
                    metrics.asr_start_time = time.time()
                    chunk_queue.put(("timeline", {"event_type": "asr_start"}))
                    logger.warning("[ASR] 批处理模式：未找到 audio_first_frame_time，使用当前时间")
                
                transcription_result = pipeline.transcribe(audio_data, audio_format, prompt=asr_prompt)
                metrics.asr_end_time = time.time()
                # 🆕 记录 ASR 结束（时间轴关键点6）
                chunk_queue.put(("timeline", {"event_type": "asr_end"}))
                
                chunk_queue.put(("chunk", {"type": "transcription", "text": transcription_result}))

                # Step 2: 热点内容作为可选素材传给 AI，由 AI 判断是否/何时自然引入
                # Step 3: 生成回复
                if pending_hot_content and CONTENT_INJECTION_ENABLED:
                    logger.info(f"[热点轨] 传入可选素材: {pending_hot_content.get('topic', '')}")
                    
                    # 🔧 修复：在发起 LLM 请求前记录 llm_start（附带时间戳）
                    llm_start_ts = int(time.time() * 1000)
                    chunk_queue.put(("timeline", {"event_type": "llm_start", "timestamp_ms": llm_start_ts}))
                    
                    for chunk in pipeline.generate_response_with_content(
                        user_text=transcription_result,
                        hot_content=pending_hot_content,
                        conversation_history=conversation_history,
                        user_profile=user_profile
                    ):
                        chunk_queue.put(("chunk", chunk))
                    # 注意：不立即清空 pending，让 AI 可以在后续轮次继续使用
                else:
                    # 正常 LLM 流程（无热点素材），🆕 带性能指标 + Layer 2 记忆
                    # 🆕 获取三层记忆上下文（包含会话摘要）
                    llm_memory_context = ""
                    if memory_context and memory_context.get("memory"):
                        try:
                            llm_memory_context = memory_context["memory"].get_context_for_llm()
                            if llm_memory_context:
                                logger.info(f"[Memory] 🧠 Layer 2 已启用, context 长度: {len(llm_memory_context)}")
                        except Exception as e:
                            logger.warning(f"[Memory] 获取 context 失败: {e}")
                    
                    # 🔧 修复：在发起 LLM 请求前记录 llm_start（附带时间戳）
                    llm_start_ts = int(time.time() * 1000)
                    chunk_queue.put(("timeline", {"event_type": "llm_start", "timestamp_ms": llm_start_ts}))
                    
                    for chunk in pipeline.process_text(
                        user_text=transcription_result,
                        conversation_history=conversation_history,
                        user_profile=user_profile,
                        memory_context=llm_memory_context,  # 🆕 传入 Layer 2 会话摘要
                        metrics=metrics
                    ):
                        chunk_queue.put(("chunk", chunk))
                
                # 🆕 发送性能指标
                chunk_queue.put(("metrics", metrics.to_dict()))
                chunk_queue.put(("done", None))
            except Exception as e:
                logger.error(f"交互轨错误: {e}")
                chunk_queue.put(("error", str(e)))

        thread = threading.Thread(target=run_interaction, daemon=True)
        thread.start()

        if pending_hot_content and CONTENT_INJECTION_ENABLED:
            logger.info(f"[交互轨] GPT-4o 启动 (待判断注入: {pending_hot_content.get('topic', 'unknown')})")
        else:
            logger.info("[交互轨] GPT-4o 三段链路启动")

        # 🆕 学习自 UserGenie: 发送 AI 回复开始信号
        # 告诉前端可以开始检测打断了，重置 isInterrupting 标志
        try:
            await websocket.send_json({
                "type": "ai_response_started",
                "message": "AI is generating response",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            logger.info("[AI] 发送 ai_response_started 信号")
        except Exception as e:
            logger.warning(f"[AI] 发送 ai_response_started 失败: {e}")

        # 消费交互轨输出
        transcription = ""
        full_response = ""
        llm_stage_sent = False  # 标记是否已发送 LLM 阶段
        
        # 🆕 Thinking Indicator（参考 UserGenie）
        # LLM 响应 > 3秒时显示"思考中..."
        THINKING_TIMEOUT_SECONDS = 3.0
        thinking_indicator_sent = False
        thinking_timer_task = None
        first_text_chunk_received = False
        
        async def send_thinking_indicator():
            """3秒后发送思考中提示"""
            nonlocal thinking_indicator_sent
            await asyncio.sleep(THINKING_TIMEOUT_SECONDS)
            if not first_text_chunk_received and not thinking_indicator_sent:
                thinking_indicator_sent = True
                try:
                    await websocket.send_json({
                        "type": "thinking_indicator",
                        "message": "AI is thinking...",
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    })
                    logger.info("[Thinking] ⏳ 发送思考中提示（LLM 响应 > 3秒）")
                except Exception as e:
                    logger.warning(f"[Thinking] 发送失败: {e}")

        while True:
            try:
                msg_type, data = await loop.run_in_executor(
                    None, lambda: chunk_queue.get(timeout=120)
                )

                if msg_type == "done":
                    # 🔧 修复：记录 LLM 结束（时间轴关键点9），使用显式时间戳
                    if pipeline_context and not pipeline_context.get("llm_timeline_ended"):
                        pipeline_context["llm_timeline_ended"] = True
                        llm_end_timestamp_ms = int(time.time() * 1000)  # 🔧 修复：使用显式时间戳
                        record_timeline_event(
                            user_id=user_id, conversation_id=conversation_id,
                            round_id=pipeline_context.get("current_round_id", 0),
                            event_type="llm_end",
                            timestamp_ms=llm_end_timestamp_ms,  # 🔧 修复：显式传递时间戳
                            message_round_id=pipeline_context.get("active_message_round_id")
                        )
                    # 🆕 清理 Thinking Indicator 计时器
                    if thinking_timer_task and not thinking_timer_task.done():
                        thinking_timer_task.cancel()
                    break
                elif msg_type == "error":
                    await websocket.send_json({"type": "error", "message": data})
                    return
                elif msg_type == "chunk":
                    chunk = data
                    # 🆕 空值检查，防止 NoneType 错误
                    if chunk is None:
                        logger.warning("[DEBUG] 收到空 chunk，跳过")
                        continue
                    chunk_type = chunk.get("type")

                    if chunk_type == "transcription":
                        transcription = chunk.get("text", "")
                        # 发送转录（带 message_round_id）
                        await websocket.send_json({
                            "type": "transcription",
                            "text": transcription,
                            "message_round_id": message_round_id,
                            "timestamp": datetime.utcnow().isoformat() + "Z"
                        })
                        # ASR 完成后，发送 LLM 阶段（让前端创建 AI 消息容器）
                        await websocket.send_json({
                            "type": "processing", 
                            "stage": "llm",
                            "message_round_id": pipeline_context.get("active_message_round_id") if pipeline_context else message_round_id
                        })
                        llm_stage_sent = True
                        
                        # 🆕 启动 Thinking Indicator 计时器
                        thinking_timer_task = asyncio.create_task(send_thinking_indicator())

                        # 🚀 通知评估轨：转录已就绪（触发阶段1+2）
                        shared_transcription["text"] = transcription
                        transcription_ready.set()
                        logger.info(f"[交互轨] ASR 完成，通知评估轨启动阶段1+2")

                    elif chunk_type == "filler_audio":
                        # 🆕 Backchanneling 填充音（降低心理延迟感）
                        # 将填充音作为 audio_chunk 发送，前端可以立即播放
                        logger.info("[Pipeline] 发送填充音到前端")
                        await websocket.send_json({
                            "type": "audio_chunk",
                            "data": chunk.get("data"),
                            "is_filler": True  # 标记为填充音
                        })
                        # 标记 AI 开始说话
                        if interrupt_state and not interrupt_state.get("is_speaking"):
                            interrupt_state["is_speaking"] = True

                    elif chunk_type == "text_chunk":
                        # 如果尚未发送 LLM 阶段，先发送
                        if not llm_stage_sent:
                            await websocket.send_json({
                                "type": "processing", 
                                "stage": "llm",
                                "message_round_id": pipeline_context.get("active_message_round_id") if pipeline_context else message_round_id
                            })
                            llm_stage_sent = True
                        
                        # 🆕 收到第一个 text_chunk，取消 Thinking Indicator
                        if not first_text_chunk_received:
                            first_text_chunk_received = True
                            # 🆕 记录 LLM 首 Token（时间轴关键点8）
                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0),
                                event_type="llm_first_token",
                                message_round_id=pipeline_context.get("active_message_round_id")
                            )
                            if thinking_timer_task and not thinking_timer_task.done():
                                thinking_timer_task.cancel()
                            # 如果已经发送了 thinking_indicator，发送结束消息
                            if thinking_indicator_sent:
                                await websocket.send_json({
                                    "type": "thinking_indicator_end",
                                    "timestamp": datetime.utcnow().isoformat() + "Z"
                                })
                                logger.info("[Thinking] ✅ 收到首个 token，结束思考提示")
                        
                        full_response += chunk.get("text", "")
                        # 🆕 添加 message_round_id，让前端能关联到正确的 AI 消息
                        chunk_with_id = {
                            **chunk,
                            "message_round_id": pipeline_context.get("active_message_round_id") if pipeline_context else message_round_id
                        }
                        await websocket.send_json(chunk_with_id)

                    elif chunk_type == "audio_chunk":
                        # 🆕 检查是否被用户打断
                        if interrupt_state and interrupt_state.get("interrupt_event"):
                            if interrupt_state["interrupt_event"].is_set():
                                logger.info("[打断] 检测到中断事件，停止发送音频")
                                interrupt_state["is_speaking"] = False
                                break
                        
                        # 🆕 如果未记录 TTS 开始，使用首块音频作为兜底
                        if pipeline_context and not pipeline_context.get("tts_timeline_started"):
                            pipeline_context["tts_timeline_started"] = True
                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0),
                                event_type="tts_start",
                                message_round_id=pipeline_context.get("active_message_round_id")
                            )

                        # 🆕 标记 AI 正在说话（首次发送音频时）
                        if interrupt_state and not interrupt_state.get("is_speaking"):
                            interrupt_state["is_speaking"] = True
                            logger.info("[状态] is_speaking = True (开始发送音频)")
                            # 🆕 记录 TTS 首块（时间轴关键点11）
                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0) if pipeline_context else 0,
                                event_type="tts_first_chunk",
                                message_round_id=pipeline_context.get("active_message_round_id") if pipeline_context else None
                            )
                        
                        await websocket.send_json(chunk)

                    elif chunk_type == "audio_end":
                        await websocket.send_json(chunk)
                        # 🆕 AI 说完话
                        if interrupt_state:
                            interrupt_state["is_speaking"] = False
                            logger.info("[状态] is_speaking = False (音频发送完成)")
                        
                        # 🆕 记录 TTS 结束（时间轴关键点12）
                        record_timeline_event(
                            user_id=user_id, conversation_id=conversation_id,
                            round_id=pipeline_context.get("current_round_id", 0) if pipeline_context else 0,
                            event_type="tts_end",
                            message_round_id=pipeline_context.get("active_message_round_id") if pipeline_context else None
                        )
                        
                        # 🔧 关键修复：后端发送 audio_end 时就标记轮次结束
                        # 不再等待前端的 assistant_played，避免用户抢说时被误判为"继续说话"
                        if pipeline_context:
                            pipeline_context["turn_closed"] = True
                            logger.info("[audio_end] 🔧 轮次已关闭（后端主动）")
                        
                        # 🆕 ASR 预热：AI 说完后立即初始化 ASR，用户下次说话时零延迟
                        if STREAMING_ASR_ENABLED and (DOUBAO_AVAILABLE or DEEPGRAM_AVAILABLE) and deepgram_context:
                            asyncio.create_task(prewarm_deepgram_asr(deepgram_context))

                    elif chunk_type == "done":
                        transcription = chunk.get("transcription", transcription)
                        full_response = chunk.get("response", full_response)
                        timings = chunk.get("latency", {})
                    elif chunk_type == "tts_start":
                        if pipeline_context and not pipeline_context.get("tts_timeline_started"):
                            pipeline_context["tts_timeline_started"] = True
                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0),
                                event_type="tts_start",
                                timestamp_ms=chunk.get("timestamp_ms"),
                                message_round_id=pipeline_context.get("active_message_round_id")
                            )

                elif msg_type == "metrics":
                    # 🆕 处理性能指标
                    performance_metrics = data
                    if performance_metrics:
                        logger.info(f"[性能指标] ASR={performance_metrics.get('asr_latency_ms', 0)}ms, "
                                    f"LLM_TTFT={performance_metrics.get('llm_ttft_ms', 0)}ms, "
                                    f"TTS_First={performance_metrics.get('tts_first_chunk_ms', 0)}ms, "
                                    f"Total={performance_metrics.get('total_latency_ms', 0)}ms")
                        # 🆕 记录延迟指标（监控指标）
                        if performance_metrics.get('asr_latency_ms'):
                            record_latency("asr", performance_metrics['asr_latency_ms'])
                        if performance_metrics.get('semantic_latency_ms'):
                            record_latency("semantic", performance_metrics['semantic_latency_ms'])
                        if performance_metrics.get('llm_ttft_ms'):
                            record_latency("llm_ttft", performance_metrics['llm_ttft_ms'])
                        if performance_metrics.get('llm_total_ms'):
                            record_latency("llm_total", performance_metrics['llm_total_ms'])
                        if performance_metrics.get('tts_first_chunk_ms'):
                            record_latency("tts_first", performance_metrics['tts_first_chunk_ms'])
                        if performance_metrics.get('total_latency_ms'):
                            record_latency("total", performance_metrics['total_latency_ms'])
                        if performance_metrics.get('processing_latency_ms'):
                            record_latency("processing", performance_metrics['processing_latency_ms'])
                        # 发送性能指标到前端
                        try:
                            await websocket.send_json({
                                "type": "performance_metrics",
                                "metrics": performance_metrics,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            })
                        except Exception as e:
                            logger.warning(f"[性能指标] 发送失败: {e}")
                
                elif msg_type == "timeline":
                    # 🆕 处理时间轴事件（来自子线程）
                    event_type = data.get("event_type")
                    if event_type:
                        record_timeline_event(
                            user_id=user_id, conversation_id=conversation_id,
                            round_id=pipeline_context.get("current_round_id", 0) if pipeline_context else 0,
                            event_type=event_type,
                            timestamp_ms=data.get("timestamp_ms"),
                            message_round_id=pipeline_context.get("active_message_round_id") if pipeline_context else None,
                            metadata=data.get("metadata")
                        )
                
                elif msg_type == "meta":
                    # 处理元数据（如注入状态）
                    meta_data = data
                    if meta_data and meta_data.get("injected_topic"):
                        injected_topic = meta_data["injected_topic"]
                        logger.info(f"[热点轨] 成功注入话题: {injected_topic}")
                        # 🆕 在热点池中标记对应的热点为已使用
                        if hot_content_context:
                            current_turn = hot_content_context.get("turn_count", 0)
                            for hot in hot_content_context.get("pool", []):
                                if hot.get("topic") == injected_topic and not hot.get("used"):
                                    mark_hot_content_used(hot_content_context, hot, current_turn)
                                    break
                        # 通知前端
                        await websocket.send_json({
                            "type": "hot_content_injected",
                            "topic": injected_topic
                        })

            except Exception as e:
                import traceback
                logger.error(f"交互轨队列错误: {e}\n{traceback.format_exc()}")
                break

        # ========== 更新对话历史 + 记忆管理 ==========
        if transcription:
            conversation_history.append({"role": "user", "content": transcription})
            # 🆕 记录消息计数（监控指标）
            increment("total_messages")
            increment("user_messages")
            # 🆕 添加到记忆管理器
            if memory_context and memory_context.get("memory"):
                memory_context["memory"].add_message("user", transcription)
        
        if full_response:
            conversation_history.append({"role": "assistant", "content": full_response})
            # 🆕 添加到记忆管理器
            if memory_context and memory_context.get("memory"):
                memory_context["memory"].add_message("assistant", full_response)

        # 🆕 使用记忆管理器的 Token-Aware 截断替代简单的轮数截断
        if memory_context and memory_context.get("memory"):
            memory = memory_context["memory"]
            logger.info(f"[Memory] 更新后状态: {memory.get_stats()}")
            
            # 检查是否需要生成摘要
            if memory.summary_pending:
                asyncio.create_task(_generate_memory_summary_async(memory, websocket))
        else:
            # 降级：使用原有的简单截断
            if len(conversation_history) > 20:
                conversation_history[:] = conversation_history[-20:]

        # ========== 翻译轨已移除，改为按需翻译（用户点击翻译按钮时调用 /api/translate）==========

        # ========== 🆕 每轮话题检测 + 热点搜索（不依赖评估轨）==========
        if CONTENT_INJECTION_ENABLED and hot_content_context is not None and transcription:
            current_turn = hot_content_context.get("turn_count", 0)
            searched_topics = hot_content_context.get("searched_topics", set())
            
            # 使用 LLM 提取话题
            async def extract_and_search_topic():
                try:
                    from providers.llm import create_llm_provider
                    llm = create_llm_provider()
                    
                    # 从用户画像提取已知兴趣
                    known_interests = []
                    if user_profile:
                        profile_interests = user_profile.get("interests", [])
                        for interest in profile_interests:
                            if isinstance(interest, dict) and "tags" in interest:
                                known_interests.extend(interest.get("tags", []))
                            elif isinstance(interest, str):
                                known_interests.append(interest)
                    
                    user_prompt = f"""Extract the main topic from this user's speech that would be good for searching trending news.

User's speech: "{transcription}"
User's known interests: {known_interests[:10] if known_interests else 'unknown'}

Rules:
- Only extract if there's a SPECIFIC topic (basketball, cooking, Taylor Swift, AI, etc.)
- Skip generic topics like "English", "learning", "practice"
- Topic should be searchable for current news/trends
- Return just the topic word/phrase in lowercase
- If no clear topic, return "none"

Output: topic only"""

                    response = llm.chat(
                        messages=[
                            {"role": "system", "content": "Extract topic. Output only the topic word."},
                            {"role": "user", "content": user_prompt}
                        ],
                        max_tokens=20,
                        temperature=0.1
                    )
                    
                    topic = response.strip().lower().replace('"', '').replace("'", "")
                    
                    if topic and topic != "none" and len(topic) < 50 and topic not in searched_topics:
                        logger.info(f"[热点轨] 🎯 LLM 提取话题: {topic} | Turn {current_turn}")
                        searched_topics.add(topic)
                        hot_content_context["searched_topics"] = searched_topics
                        
                        # 异步搜索热点内容
                        try:
                            injector = get_injector()
                            cefr_level = user_profile.get('cefr_level', 'B1') if user_profile else 'B1'
                            content = await asyncio.wait_for(
                                injector.fetch_for_topic_async(topic, cefr_level),
                                timeout=10
                            )
                            if content:
                                add_to_pool(
                                    hot_content_context,
                                    topic=content.topic,
                                    headline=content.headline,
                                    detail=content.detail,
                                    search_turn=current_turn
                                )
                                logger.info(f"[热点轨] ✅ 热点入池: {content.topic}")
                        except asyncio.TimeoutError:
                            logger.warning(f"[热点轨] 热点搜索超时: {topic}")
                        except Exception as e:
                            logger.warning(f"[热点轨] 热点搜索失败: {e}")
                    elif topic and topic in searched_topics:
                        logger.debug(f"[热点轨] ⏭️ 话题已搜索过: {topic}")
                        
                except Exception as e:
                    logger.warning(f"[热点轨] 话题提取失败: {e}")
            
            # 启动异步任务（不阻塞主流程）
            asyncio.create_task(extract_and_search_topic())
            hot_content_context["turn_count"] = current_turn + 1

        # ========== 保存消息到数据库 ==========
        if conversation_id and (transcription or full_response):
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
                    logger.info(f"[消息] 已保存 {len(messages_to_save)} 条消息")
            except Exception as e:
                logger.error(f"保存消息失败: {e}")

        # ========== 摘要生成（第一轮）==========
        if conversation_id and round_number == 1 and transcription and full_response:
            asyncio.create_task(
                generate_conversation_summary_async(conversation_id, transcription, full_response, websocket)
            )

        # ========== 发送完成信号 ==========
        # 🆕 确保发送 audio_end（用于自动对话模式恢复 VAD）
        await websocket.send_json({"type": "audio_end"})
        
        timings["total"] = round(time.time() - total_start, 2)
        await websocket.send_json({
            "type": "done",
            "latency": timings
        })

        # 🔧 启动 turn_closed 超时兜底
        await start_turn_closed_timeout()

        logger.info(f"[性能] 总耗时: {timings['total']}s")

    except Exception as e:
        logger.error(f"处理音频错误: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "message": str(e)})


async def process_audio_stream_with_transcription(
    websocket: WebSocket,
    pipeline: GPT4oPipeline,
    processor: UnifiedProcessor,
    transcription: str,
    audio_data: bytes,
    audio_format: str,
    conversation_history: list,
    user_profile: dict,
    user_id: Optional[str],
    user_repo,
    conversation_id: Optional[str],
    eval_context: dict,
    pending_hot_content: Optional[Dict[str, Any]] = None,
    hot_content_context: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
    message_round_id: Optional[str] = None,
    interrupt_state: Optional[Dict[str, Any]] = None,
    pipeline_context: Optional[Dict[str, Any]] = None,  # 🆕 用于监听用户继续说话
    tts_delay: float = 0.5  # 🆕 TTS 播放延迟（缓冲期）
):
    """
    处理已转录的音频 - LLM 生成 + TTS
    
    支持在处理过程中检测用户继续说话并中断。
    """
    timings = {"stt": 0}  # STT 已预先完成
    total_start = time.time()
    
    # 🆕 初始化打断事件
    if interrupt_state is not None:
        interrupt_state["interrupt_event"] = asyncio.Event()
        interrupt_state["is_speaking"] = False

    try:
        if not transcription or transcription.strip() == "":
            await websocket.send_json({"type": "error", "message": "转录为空"})
            return

        logger.info(f"[双阈值] 使用预启动转录: {transcription[:50]}...")
        
        # 🔧 发送转录结果给前端（让用户看到自己说的话）
        try:
            await websocket.send_json({
                "type": "transcription",
                "text": transcription,
                "is_final": True,
                "message_round_id": message_round_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            logger.info(f"[双阈值] 已发送转录给前端: message_round_id={message_round_id}, text={transcription[:30]}...")
        except Exception as e:
            logger.warning(f"[双阈值] 发送转录失败: {e}")
        
        # 🆕 发送 ai_response_started 信号（重置前端 isInterrupting 标志）
        try:
            await websocket.send_json({
                "type": "ai_response_started",
                "message": "AI is generating response (with transcription)",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            logger.info("[AI-with-transcription] 发送 ai_response_started 信号")
        except Exception as e:
            logger.warning(f"[AI-with-transcription] 发送 ai_response_started 失败: {e}")
        
        # 发送 LLM 阶段
        await websocket.send_json({
            "type": "processing", 
            "stage": "llm",
            "message_round_id": pipeline_context.get("active_message_round_id") if pipeline_context else None
        })

        loop = asyncio.get_event_loop()
        round_number = len([m for m in conversation_history if m.get("role") == "user"]) + 1
        if not message_round_id:
            message_round_id = f"{conversation_id}_{round_number}" if conversation_id else f"msg_{round_number}"

        # ========== 评估轨（异步）==========
        eval_semaphore = eval_context["semaphore"]
        eval_tasks = eval_context["tasks"]
        eval_context["counter"][0] += 1
        current_order = eval_context["counter"][0]

        transcription_ready = asyncio.Event()
        shared_transcription = {"text": transcription}
        transcription_ready.set()  # 已有转录，直接设置

        async def run_evaluation_async():
            """评估轨 - 使用预启动的转录"""
            eval_start = time.time()
            logger.info(f"[评估轨-双阈值] 启动评估, transcription={transcription[:30]}...")

            # 评分节奏控制：非指定轮次跳过评估
            if EVALUATION_CADENCE_TURNS > 1 and (current_order % EVALUATION_CADENCE_TURNS) != 0:
                # 🔴 修复：通知前端评估被跳过（减少 pendingEvaluations）
                try:
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "cadence"
                    })
                except:
                    pass
                return

            try:
                await asyncio.wait_for(eval_semaphore.acquire(), timeout=0.1)
            except asyncio.TimeoutError:
                logger.warning(f"[评估轨-双阈值] 队列已满，跳过")
                try:
                    await websocket.send_json({
                        "type": "evaluation_skipped",
                        "message_round_id": message_round_id,
                        "order": current_order,
                        "reason": "queue_full"
                    })
                except:
                    pass
                return

            try:
                aggregated_transcription = _aggregate_recent_user_texts(
                    conversation_history,
                    transcription.strip(),
                    EVALUATION_AGGREGATE_TURNS
                )
                if not aggregated_transcription:
                    try:
                        await websocket.send_json({
                            "type": "evaluation_skipped",
                            "message_round_id": message_round_id,
                            "order": current_order,
                            "reason": "empty_transcription"
                        })
                    except:
                        pass
                    return

                evaluation_track = get_evaluation_track()
                eval_result = await evaluation_track.evaluate(
                    transcription=aggregated_transcription,
                    audio_data=audio_data,
                    audio_format=audio_format,
                    user_profile=user_profile
                )

                eval_time = time.time() - eval_start
                final_evaluation = eval_result.to_dict()

                if final_evaluation.get("overall_score") is not None:
                    from services.unified_processor import ProcessingResult
                    result_obj = ProcessingResult(
                        transcription=transcription,
                        evaluation=final_evaluation,
                        interests=[],
                        ai_feedback="",
                        next_question="",
                        full_response=""
                    )
                    UserProfileUpdater.update(user_profile, result_obj)

                score = final_evaluation.get("overall_score", 0)
                calculated_level = UserProfileUpdater._score_to_cefr(score)
                final_evaluation["cefr_level"] = calculated_level

                await websocket.send_json({
                    "type": "evaluation",
                    "data": final_evaluation,
                    "message_round_id": message_round_id,
                    "order": current_order,
                    "latency": round(eval_time, 2)
                })

                logger.info(f"[评估轨-双阈值] 完成, 耗时: {eval_time:.2f}s")

            except Exception as e:
                logger.error(f"[评估轨-双阈值] 失败: {e}")
            finally:
                eval_semaphore.release()
                if message_round_id in eval_tasks:
                    del eval_tasks[message_round_id]

        eval_task = asyncio.create_task(run_evaluation_async())
        eval_tasks[message_round_id] = eval_task

        # ========== 🆕 热点触发逻辑（Recovery 模式）==========
        # 触发规则：
        # 1. 话题陷入死胡同：consecutive_short >= 2 或 strategy == 'switch_topic'
        # 2. 满足注入频率限制：间隔 >= min_interval 且 count < max_inject
        if CONTENT_INJECTION_ENABLED and hot_content_context is not None:
            # 更新轮次计数
            hot_content_context["turn_count"] = round_number
            
            # 节奏分析
            from services.unified_processor import ConversationRhythmAnalyzer
            rhythm_hints = ConversationRhythmAnalyzer.analyze(transcription, conversation_history)
            strategy = rhythm_hints.get("suggested_strategy", "continue")
            consecutive_short = rhythm_hints.get("consecutive_short_count", 0)
            
            # 检查是否需要触发热点（Recovery 模式）
            need_recovery = strategy == "switch_topic" or consecutive_short >= 2
            can_inject = (
                hot_content_context["inject_count"] < hot_content_context["max_inject"] and
                round_number - hot_content_context["last_inject_turn"] >= hot_content_context["min_interval"]
            )
            
            if need_recovery and can_inject and not pending_hot_content:
                logger.info(f"[热点轨] Recovery 触发: strategy={strategy}, consecutive_short={consecutive_short}")
                
                # 选择搜索话题：用户兴趣或通用话题
                import random
                user_interests = user_profile.get('interests', []) if user_profile else []
                if user_interests:
                    search_topic = random.choice(user_interests)
                else:
                    from config.constants import GENERAL_HOT_TOPICS
                    search_topic = random.choice(GENERAL_HOT_TOPICS)
                
                last_topic = hot_content_context.get("last_topic")
                if search_topic != last_topic:
                    hot_content_context["last_topic"] = search_topic
                    
                    # 异步搜索热点（Recovery 模式）
                    async def recovery_search_async():
                        try:
                            injector = get_injector()
                            cefr_level = user_profile.get('cefr_level', 'B1') if user_profile else 'B1'
                            content = await asyncio.wait_for(
                                injector.fetch_for_topic_async(search_topic, cefr_level),
                                timeout=8
                            )
                            if content:
                                hot_content_context["pending"] = {
                                    "topic": content.topic,
                                    "headline": content.headline,
                                    "detail": content.detail
                                }
                                hot_content_context["last_inject_turn"] = round_number
                                hot_content_context["inject_count"] += 1
                                logger.info(f"[热点轨] Recovery 热点就绪: {content.headline[:50]}...")
                        except asyncio.TimeoutError:
                            logger.warning(f"[热点轨] Recovery 搜索超时: {search_topic}")
                        except Exception as e:
                            logger.warning(f"[热点轨] Recovery 搜索失败: {e}")
                    
                    # 启动异步任务
                    asyncio.create_task(recovery_search_async())

        # ========== 交互轨（跳过 STT）==========
        chunk_queue = queue.Queue()

        def run_interaction():
            """在线程中运行 LLM + TTS（跳过 STT）"""
            try:
                # 🆕 创建性能指标追踪器（跳过 ASR）
                metrics = PerformanceMetrics()
                metrics.user_stop_speaking_time = time.time()
                
                # 🔧 修复：ASR 时间轴（双阈值模式）
                # - asr_start: 使用收到第一帧音频的时间（已在前面记录）
                # - asr_end: 使用当前时间（收到最终转录）
                asr_start_ms = pipeline_context.get("audio_first_frame_time") if pipeline_context else 0
                asr_end_ms = int(time.time() * 1000)
                
                if asr_start_ms:
                    metrics.asr_start_time = asr_start_ms / 1000.0
                else:
                    metrics.asr_start_time = metrics.user_stop_speaking_time
                    asr_start_ms = int(metrics.user_stop_speaking_time * 1000)
                metrics.asr_end_time = time.time()
                
                # 🔧 只补齐 asr_end（asr_start 已在收到首帧音频时记录）
                if not (pipeline_context and pipeline_context.get("asr_timeline_started")):
                    # 如果之前没记录 asr_start，这里补齐
                    chunk_queue.put(("timeline", {"event_type": "asr_start", "timestamp_ms": asr_start_ms}))
                chunk_queue.put(("timeline", {"event_type": "asr_end", "timestamp_ms": asr_end_ms}))
                
                # 🆕 读取语义检测时间（从 pipeline_context）
                if pipeline_context:
                    metrics.semantic_start_time = pipeline_context.get("semantic_start_time", 0)
                    metrics.semantic_end_time = pipeline_context.get("semantic_end_time", 0)
                
                # 热点内容作为可选素材传给 AI，由 AI 判断是否/何时自然引入
                if pending_hot_content and CONTENT_INJECTION_ENABLED:
                    logger.info(f"[热点轨-双阈值] 传入可选素材: {pending_hot_content.get('topic', '')}")
                    
                    # 🔧 修复：在发起 LLM 请求前记录 llm_start（附带时间戳）
                    llm_start_ts = int(time.time() * 1000)
                    chunk_queue.put(("timeline", {"event_type": "llm_start", "timestamp_ms": llm_start_ts}))
                    
                    for chunk in pipeline.generate_response_with_content(
                        user_text=transcription,
                        hot_content=pending_hot_content,
                        conversation_history=conversation_history,
                        user_profile=user_profile
                    ):
                        chunk_queue.put(("chunk", chunk))
                    # 注意：不立即清空 pending，让 AI 可以在后续轮次继续使用
                    # 只有当 AI 实际使用了才清空（需要从 AI 回复中检测）
                else:
                    # 🆕 带性能指标 + Layer 2 记忆
                    # 🆕 获取三层记忆上下文（包含会话摘要）
                    llm_memory_context = ""
                    if memory_context and memory_context.get("memory"):
                        try:
                            llm_memory_context = memory_context["memory"].get_context_for_llm()
                            if llm_memory_context:
                                logger.info(f"[Memory] 🧠 Layer 2 已启用(双阈值), context 长度: {len(llm_memory_context)}")
                        except Exception as e:
                            logger.warning(f"[Memory] 获取 context 失败(双阈值): {e}")
                    
                    # 🔧 修复：在发起 LLM 请求前记录 llm_start（附带时间戳）
                    llm_start_ts = int(time.time() * 1000)
                    chunk_queue.put(("timeline", {"event_type": "llm_start", "timestamp_ms": llm_start_ts}))
                    
                    for chunk in pipeline.process_text(
                        user_text=transcription,
                        conversation_history=conversation_history,
                        user_profile=user_profile,
                        memory_context=llm_memory_context,  # 🆕 传入 Layer 2 会话摘要
                        metrics=metrics
                    ):
                        chunk_queue.put(("chunk", chunk))
                
                # 🆕 发送性能指标
                chunk_queue.put(("metrics", metrics.to_dict()))
                chunk_queue.put(("done", None))
            except Exception as e:
                logger.error(f"交互轨错误(双阈值): {e}")
                chunk_queue.put(("error", str(e)))

        thread = threading.Thread(target=run_interaction, daemon=True)
        thread.start()

        logger.info("[交互轨-双阈值] LLM + TTS 启动（已跳过 STT）")

        # 🆕 修复: 发送 ai_response_started 信号（重置前端 isInterrupting 标志）
        try:
            await websocket.send_json({
                "type": "ai_response_started",
                "message": "AI is generating response (dual-threshold)",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            logger.info("[AI-双阈值] 发送 ai_response_started 信号")
        except Exception as e:
            logger.warning(f"[AI-双阈值] 发送 ai_response_started 失败: {e}")

        # 消费交互轨输出
        full_response = ""
        llm_start = time.time()
        is_first_audio = True  # 🆕 标记是否为第一个音频块
        llm_started = False  # 🆕 标记 LLM 是否已开始
        first_text_chunk_received = False  # 🆕 标记是否收到首个 text_chunk

        while True:
            try:
                msg_type, data = await loop.run_in_executor(
                    None, lambda: chunk_queue.get(timeout=120)
                )

                if msg_type == "done":
                    # 🔧 修复：记录 LLM 结束（时间轴关键点9），使用显式时间戳
                    if pipeline_context and not pipeline_context.get("llm_timeline_ended"):
                        pipeline_context["llm_timeline_ended"] = True
                        llm_end_timestamp_ms = int(time.time() * 1000)  # 🔧 修复：使用显式时间戳
                        record_timeline_event(
                            user_id=user_id, conversation_id=conversation_id,
                            round_id=pipeline_context.get("current_round_id", 0),
                            event_type="llm_end",
                            timestamp_ms=llm_end_timestamp_ms,  # 🔧 修复：显式传递时间戳
                            message_round_id=pipeline_context.get("active_message_round_id")
                        )
                    break
                elif msg_type == "error":
                    await websocket.send_json({"type": "error", "message": data})
                    return
                elif msg_type == "chunk":
                    chunk = data
                    # 🆕 空值检查，防止 NoneType 错误
                    if chunk is None:
                        logger.warning("[DEBUG] 收到空 chunk，跳过")
                        continue
                    chunk_type = chunk.get("type")
                    logger.info(f"[DEBUG] 收到 chunk: {chunk_type}")

                    if chunk_type == "text_chunk":
                        # 🆕 检查用户是否继续说话（取消 LLM）
                        if pipeline_context and pipeline_context.get("llm_cancelled"):
                            logger.info("[追加模式] LLM 已被取消，停止发送 text_chunk")
                            # 🚀 修复：发送明确的取消信号，让前端停止更新消息
                            try:
                                await websocket.send_json({
                                    "type": "response_cancelled",
                                    "message": "User continued speaking, response cancelled"
                                })
                            except (WebSocketDisconnect, RuntimeError):
                                pass
                            break
                        
                        # 🔧 已移动：llm_start 在发起 LLM 请求前记录（通过 queue 附带 timestamp_ms）
                        llm_started = True  # 保留标记，用于其他逻辑
                        
                        # 🆕 记录 LLM 首 Token（时间轴关键点8）
                        if not first_text_chunk_received:
                            first_text_chunk_received = True
                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0) if pipeline_context else 0,
                                event_type="llm_first_token",
                                message_round_id=message_round_id
                            )
                        
                        full_response += chunk.get("text", "")
                        # 🆕 添加 message_round_id，让前端能关联到正确的 AI 消息
                        chunk_with_id = {
                            **chunk,
                            "message_round_id": message_round_id
                        }
                        await websocket.send_json(chunk_with_id)
                    elif chunk_type == "audio_chunk":
                        # logger.info(f"[DEBUG] 处理 audio_chunk, is_first={is_first_audio}")
                        # 🆕 检查用户是否继续说话（取消 LLM）
                        if pipeline_context and pipeline_context.get("llm_cancelled"):
                            logger.info("[追加模式] LLM 已被取消，停止发送 audio_chunk")
                            if interrupt_state:
                                interrupt_state["is_speaking"] = False
                            break
                        
                        # 🆕 如果未记录 TTS 开始，使用首块音频作为兜底
                        if pipeline_context and not pipeline_context.get("tts_timeline_started"):
                            pipeline_context["tts_timeline_started"] = True
                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0),
                                event_type="tts_start",
                                message_round_id=message_round_id
                            )
                        
                        # 🆕 TTS 缓冲逻辑 (Optimistic Execution)
                        if is_first_audio:
                            is_first_audio = False
                            if tts_delay > 0:
                                logger.info(f"[TTS] 启动缓冲延迟: {tts_delay}s (状态: {pipeline_context.get('llm_status', 'UNKNOWN')})")
                                start_wait = time.time()
                                while time.time() - start_wait < tts_delay:
                                     # 在缓冲期间持续检查取消信号
                                     if pipeline_context and pipeline_context.get("llm_cancelled"):
                                         logger.info("[TTS] 缓冲期间检测到取消信号，彻底丢弃输出")
                                         if interrupt_state:
                                             interrupt_state["is_speaking"] = False
                                         return # 直接退出函数
                                     # 同时也检查打断信号
                                     if interrupt_state and interrupt_state.get("interrupt_event") and interrupt_state["interrupt_event"].is_set():
                                         logger.info("[TTS] 缓冲期间检测到打断信号，彻底丢弃输出")
                                         if interrupt_state:
                                             interrupt_state["is_speaking"] = False
                                         return
                                     await asyncio.sleep(0.1)
                                logger.info(f"[TTS] 缓冲结束，开始播放")

                        # 🆕 检查是否被用户打断
                        if interrupt_state and interrupt_state.get("interrupt_event"):
                            if interrupt_state["interrupt_event"].is_set():
                                logger.info("[打断] 检测到中断事件，停止发送音频")
                                interrupt_state["is_speaking"] = False
                                break
                        
                        # 🆕 标记 AI 正在说话
                        if interrupt_state and not interrupt_state.get("is_speaking"):
                            interrupt_state["is_speaking"] = True
                            logger.info("[状态] is_speaking = True")
                            # 🆕 记录 TTS 首块（时间轴关键点11）
                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0) if pipeline_context else 0,
                                event_type="tts_first_chunk",
                                message_round_id=message_round_id
                            )
                        
                        await websocket.send_json(chunk)
                    elif chunk_type == "audio_end":
                        # 🆕 检查取消状态
                        if pipeline_context and pipeline_context.get("llm_cancelled"):
                             break
                        await websocket.send_json(chunk)
                        # 🆕 AI 说完话
                        if interrupt_state:
                            interrupt_state["is_speaking"] = False
                            logger.info("[状态] is_speaking = False (双阈值)")
                        
                        # 🆕 记录 TTS 结束（时间轴关键点12）
                        record_timeline_event(
                            user_id=user_id, conversation_id=conversation_id,
                            round_id=pipeline_context.get("current_round_id", 0) if pipeline_context else 0,
                            event_type="tts_end",
                            message_round_id=message_round_id
                        )
                        
                        # 🔧 关键修复：后端发送 audio_end 时就标记轮次结束
                        if pipeline_context:
                            pipeline_context["turn_closed"] = True
                            logger.info("[audio_end] 🔧 轮次已关闭（双阈值模式）")
                    elif chunk_type == "done":
                        full_response = chunk.get("response", full_response)
                        latency = chunk.get("latency")
                        if latency and isinstance(latency, dict):
                            timings.update(latency)
                    elif chunk_type == "tts_start":
                        if pipeline_context and not pipeline_context.get("tts_timeline_started"):
                            pipeline_context["tts_timeline_started"] = True
                            record_timeline_event(
                                user_id=user_id, conversation_id=conversation_id,
                                round_id=pipeline_context.get("current_round_id", 0),
                                event_type="tts_start",
                                timestamp_ms=chunk.get("timestamp_ms"),
                                message_round_id=message_round_id
                            )

                elif msg_type == "meta":
                    meta_data = data
                    if meta_data and meta_data.get("injected_topic"):
                        # 🆕 在热点池中标记对应的热点为已使用
                        if hot_content_context:
                            injected_topic = meta_data["injected_topic"]
                            current_turn = hot_content_context.get("turn_count", 0)
                            for hot in hot_content_context.get("pool", []):
                                if hot.get("topic") == injected_topic and not hot.get("used"):
                                    mark_hot_content_used(hot_content_context, hot, current_turn)
                                    break
                        await websocket.send_json({
                            "type": "hot_content_injected",
                            "topic": meta_data["injected_topic"]
                        })

                elif msg_type == "metrics":
                    # 🆕 处理性能指标（双阈值模式）
                    performance_metrics = data
                    if performance_metrics:
                        logger.info(f"[性能指标-双阈值] ASR={performance_metrics.get('asr_latency_ms', 0)}ms, "
                                    f"Semantic={performance_metrics.get('semantic_latency_ms', 0)}ms, "
                                    f"LLM_TTFT={performance_metrics.get('llm_ttft_ms', 0)}ms, "
                                    f"TTS_First={performance_metrics.get('tts_first_chunk_ms', 0)}ms, "
                                    f"Total={performance_metrics.get('total_latency_ms', 0)}ms")
                        # 记录延迟指标（监控指标）
                        if performance_metrics.get('asr_latency_ms'):
                            record_latency("asr", performance_metrics['asr_latency_ms'])
                        if performance_metrics.get('semantic_latency_ms'):
                            record_latency("semantic", performance_metrics['semantic_latency_ms'])
                        if performance_metrics.get('llm_ttft_ms'):
                            record_latency("llm_ttft", performance_metrics['llm_ttft_ms'])
                        if performance_metrics.get('llm_total_ms'):
                            record_latency("llm_total", performance_metrics['llm_total_ms'])
                        if performance_metrics.get('tts_first_chunk_ms'):
                            record_latency("tts_first", performance_metrics['tts_first_chunk_ms'])
                        if performance_metrics.get('total_latency_ms'):
                            record_latency("total", performance_metrics['total_latency_ms'])
                        if performance_metrics.get('processing_latency_ms'):
                            record_latency("processing", performance_metrics['processing_latency_ms'])
                        # 发送性能指标到前端
                        try:
                            await websocket.send_json({
                                "type": "performance_metrics",
                                "metrics": performance_metrics,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            })
                        except Exception as e:
                            logger.warning(f"[性能指标-双阈值] 发送失败: {e}")

                elif msg_type == "timeline":
                    # 🆕 处理时间轴事件（来自子线程，双阈值模式）
                    event_type = data.get("event_type")
                    if event_type:
                        record_timeline_event(
                            user_id=user_id, conversation_id=conversation_id,
                            round_id=pipeline_context.get("current_round_id", 0) if pipeline_context else 0,
                            event_type=event_type,
                            timestamp_ms=data.get("timestamp_ms"),
                            message_round_id=pipeline_context.get("active_message_round_id") if pipeline_context else message_round_id,
                            metadata=data.get("metadata")
                        )

            except Exception as e:
                import traceback
                logger.error(f"交互轨队列错误(双阈值): {e}\n{traceback.format_exc()}")
                break

        timings["llm_tts"] = round(time.time() - llm_start, 2)
        
        # 🆕 检查是否被取消（用户继续说话）
        was_cancelled = pipeline_context and pipeline_context.get("llm_cancelled")
        if was_cancelled:
            logger.info("[追加模式] LLM 被取消，不保存不完整的对话")
            # 🚀 修复：确保发送取消信号（如果之前没有发送）
            try:
                await websocket.send_json({
                    "type": "response_cancelled",
                    "message": "User continued speaking, response cancelled"
                })
            except (WebSocketDisconnect, RuntimeError):
                pass
            # 不更新对话历史，等用户说完后重新处理
            return

        # ========== 更新对话历史 ==========
        if transcription:
            conversation_history.append({"role": "user", "content": transcription})
            if memory_context and memory_context.get("memory"):
                memory_context["memory"].add_message("user", transcription)

        if full_response:
            conversation_history.append({"role": "assistant", "content": full_response})
            if memory_context and memory_context.get("memory"):
                memory_context["memory"].add_message("assistant", full_response)

        if memory_context and memory_context.get("memory"):
            memory = memory_context["memory"]
            if memory.summary_pending:
                asyncio.create_task(_generate_memory_summary_async(memory, websocket))
        else:
            if len(conversation_history) > 20:
                conversation_history[:] = conversation_history[-20:]

        # ========== 🆕 每轮话题检测 + 热点搜索（双阈值模式）==========
        if CONTENT_INJECTION_ENABLED and hot_content_context is not None and transcription:
            current_turn = hot_content_context.get("turn_count", 0)
            searched_topics = hot_content_context.get("searched_topics", set())
            
            # 使用 LLM 提取话题
            async def extract_and_search_topic_dual():
                try:
                    from providers.llm import create_llm_provider
                    llm = create_llm_provider()
                    
                    # 从用户画像提取已知兴趣
                    known_interests = []
                    if user_profile:
                        profile_interests = user_profile.get("interests", [])
                        for interest in profile_interests:
                            if isinstance(interest, dict) and "tags" in interest:
                                known_interests.extend(interest.get("tags", []))
                            elif isinstance(interest, str):
                                known_interests.append(interest)
                    
                    user_prompt = f"""Extract the main topic from this user's speech that would be good for searching trending news.

User's speech: "{transcription}"
User's known interests: {known_interests[:10] if known_interests else 'unknown'}

Rules:
- Only extract if there's a SPECIFIC topic (basketball, cooking, Taylor Swift, AI, etc.)
- Skip generic topics like "English", "learning", "practice"
- Topic should be searchable for current news/trends
- Return just the topic word/phrase in lowercase
- If no clear topic, return "none"

Output: topic only"""

                    response = llm.chat(
                        messages=[
                            {"role": "system", "content": "Extract topic. Output only the topic word."},
                            {"role": "user", "content": user_prompt}
                        ],
                        max_tokens=20,
                        temperature=0.1
                    )
                    
                    topic = response.strip().lower().replace('"', '').replace("'", "")
                    
                    if topic and topic != "none" and len(topic) < 50 and topic not in searched_topics:
                        logger.info(f"[热点轨-双阈值] 🎯 LLM 提取话题: {topic} | Turn {current_turn}")
                        searched_topics.add(topic)
                        hot_content_context["searched_topics"] = searched_topics
                        
                        # 异步搜索热点内容
                        try:
                            injector = get_injector()
                            cefr_level = user_profile.get('cefr_level', 'B1') if user_profile else 'B1'
                            content = await asyncio.wait_for(
                                injector.fetch_for_topic_async(topic, cefr_level),
                                timeout=10
                            )
                            if content:
                                add_to_pool(
                                    hot_content_context,
                                    topic=content.topic,
                                    headline=content.headline,
                                    detail=content.detail,
                                    search_turn=current_turn
                                )
                                logger.info(f"[热点轨-双阈值] ✅ 热点入池: {content.topic}")
                        except asyncio.TimeoutError:
                            logger.warning(f"[热点轨-双阈值] 热点搜索超时: {topic}")
                        except Exception as e:
                            logger.warning(f"[热点轨-双阈值] 热点搜索失败: {e}")
                    elif topic and topic in searched_topics:
                        logger.debug(f"[热点轨-双阈值] ⏭️ 话题已搜索过: {topic}")
                        
                except Exception as e:
                    logger.warning(f"[热点轨-双阈值] 话题提取失败: {e}")
            
            # 启动异步任务（不阻塞主流程）
            asyncio.create_task(extract_and_search_topic_dual())
            hot_content_context["turn_count"] = current_turn + 1

        # ========== 保存消息 ==========
        if conversation_id and (transcription or full_response):
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
                        "metadata": {"dual_threshold": True}
                    })
                if full_response:
                    messages_to_save.append({
                        "conversation_id": clean_conversation_id,
                        "round_number": round_number,
                        "sender_role": "assistant",
                        "content": full_response,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "metadata": {"dual_threshold": True}
                    })

                if messages_to_save:
                    conv_repo.client.table("messages").insert(messages_to_save).execute()
                    logger.info(f"[消息-双阈值] 已保存 {len(messages_to_save)} 条消息")
            except Exception as e:
                logger.error(f"保存消息失败(双阈值): {e}")

        # ========== 摘要生成 ==========
        if conversation_id and round_number == 1 and transcription and full_response:
            asyncio.create_task(
                generate_conversation_summary_async(conversation_id, transcription, full_response, websocket)
            )

        # ========== 发送完成信号 ==========
        await websocket.send_json({"type": "audio_end"})

        timings["total"] = round(time.time() - total_start, 2)
        
        # 🆕 调试：记录发送给前端的性能指标
        logger.info(f"[性能-双阈值] 发送给前端的 latency: {timings}")
        
        await websocket.send_json({
            "type": "done",
            "latency": timings,
            "dual_threshold": True  # 标记使用了双阈值系统
        })

        # 🔧 启动 turn_closed 超时兜底
        await start_turn_closed_timeout()

        logger.info(f"[性能-双阈值] 总耗时: {timings['total']}s (STT 已预启动)")

    except Exception as e:
        logger.error(f"处理音频错误(双阈值): {e}", exc_info=True)
        await websocket.send_json({"type": "error", "message": str(e)})


# ========== Deepgram ASR 预热 ==========

async def prewarm_deepgram_asr(deepgram_context: dict):
    """
    ASR 预热：提前初始化 ASR 连接（支持 Deepgram / 豆包）
    
    在 AI 说话结束后调用，这样用户开始说话时连接已就绪，
    节省约 700ms 的连接建立延迟。
    """
    asr_available = (ASR_PROVIDER == "deepgram" and DEEPGRAM_AVAILABLE) or \
                   (ASR_PROVIDER == "doubao" and DOUBAO_AVAILABLE)
    if not STREAMING_ASR_ENABLED or not asr_available:
        return
    
    try:
        # 清理之前的连接
        if deepgram_context.get("asr"):
            try:
                await deepgram_context["asr"].stop_stream()
            except:
                pass
            deepgram_context["asr"] = None
        
        # 🆕 根据配置创建 ASR 实例
        if ASR_PROVIDER == "doubao" and DOUBAO_AVAILABLE:
            config = DoubaoASRConfig(language=STREAMING_ASR_LANGUAGE)
            # 🆕 使用热备份连接池
            if USE_ASR_POOL and DOUBAO_POOL_AVAILABLE:
                pool_config = PoolConfig(keepalive_interval=5.0)
                deepgram_context["asr"] = create_asr_pool(config, pool_config)
                deepgram_context["is_pool"] = True
                logger.info(f"[ASR] 🔥 豆包 ASR 热备份连接池预热完成")
            else:
                deepgram_context["asr"] = create_doubao_asr(config)
                deepgram_context["is_pool"] = False
                logger.info(f"[ASR] 豆包 ASR 预热完成")
        else:
            config = DeepgramConfig(
                language=STREAMING_ASR_LANGUAGE,
                endpointing=300,       # 300ms 静音检测
                utterance_end_ms=2000, # 🆕 参考 UserGenie: 2000ms 静默后触发 utterance_end
            )
            deepgram_context["asr"] = create_deepgram_asr(config)
            logger.info(f"[ASR] Deepgram 预热完成")
        
        deepgram_context["transcript_buffer"] = ""
        deepgram_context["last_interim_text"] = ""
        
    except Exception as e:
        logger.warning(f"[ASR] 预热失败: {e}")
        deepgram_context["asr"] = None


