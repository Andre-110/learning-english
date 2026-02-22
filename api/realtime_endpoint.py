"""
Qwen-Omni Realtime WebSocket 端点

实现实时语音对话，支持：
- 实时音频流输入
- 实时语音/文本输出
- 服务端 VAD
- 打断支持
- 异步翻译和评估
"""
import asyncio
import base64
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from services.qwen_omni_realtime import (
    QwenOmniRealtimeService,
    RealtimeConfig,
    create_realtime_service,
    DASHSCOPE_AVAILABLE
)
from services.unified_processor import UnifiedProcessor
from services.qwen_omni_audio import create_qwen_omni_service
from prompts.templates import (
    get_interaction_system_prompt,
    get_translation_system_prompt,
    get_translation_user_prompt
)
from config.constants import EVALUATION_CADENCE_TURNS, EVALUATION_AGGREGATE_TURNS
from storage.impl.supabase_repository import (
    SupabaseUserRepository,
    SupabaseConversationRepository
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.websocket("/chat")
async def realtime_chat(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None),
    conversation_id: Optional[str] = Query(None)
):
    """
    Realtime 语音对话 WebSocket 端点
    
    消息格式：
    
    客户端 -> 服务端:
    - {"type": "audio", "data": "<base64 PCM 16kHz mono 16bit>"}
    - {"type": "interrupt"}  # 打断当前响应
    - {"type": "end"}  # 结束对话
    
    服务端 -> 客户端:
    - {"type": "connected", "session_id": "..."}
    - {"type": "transcription", "text": "..."}  # 用户语音转录
    - {"type": "text_delta", "delta": "..."}  # AI 回复文本片段
    - {"type": "audio_delta", "audio": "<base64>"}  # AI 回复音频片段
    - {"type": "speech_started"}  # VAD 检测到说话开始
    - {"type": "speech_stopped"}  # VAD 检测到说话结束
    - {"type": "response_done"}  # AI 响应完成
    - {"type": "translation", "text": "..."}  # 中文翻译
    - {"type": "evaluation", "data": {...}}  # 评估结果
    - {"type": "error", "message": "..."}
    """
    await websocket.accept()
    logger.info(f"[Realtime] WebSocket 连接: user_id={user_id}, conversation_id={conversation_id}")
    
    if not DASHSCOPE_AVAILABLE:
        await websocket.send_json({
            "type": "error",
            "message": "DashScope SDK 未安装，请安装 dashscope>=1.23.9"
        })
        await websocket.close()
        return
    
    # 获取事件循环
    loop = asyncio.get_event_loop()
    
    # 加载用户画像
    user_profile = {}
    user_repo = None
    if user_id:
        try:
            user_repo = SupabaseUserRepository()
            db_profile = user_repo.get_profile(user_id)
            if db_profile:
                user_profile = db_profile.dict()
                logger.info(f"[Realtime] 加载用户画像: {user_id}, level={user_profile.get('cefr_level')}")
        except Exception as e:
            logger.warning(f"[Realtime] 加载用户画像失败: {e}")
    
    # 创建 Realtime 服务
    realtime_service = create_realtime_service()
    
    # 创建翻译和评估用的处理器
    api_service = create_qwen_omni_service()
    processor = UnifiedProcessor(api_service=api_service)
    
    # 用于收集完整响应（翻译和评估用）
    full_response_text = ""
    current_transcription = ""
    audio_buffer = []  # 收集音频用于评估
    recent_user_transcriptions = []
    
    # 评估队列管理
    eval_semaphore = asyncio.Semaphore(3)
    eval_order_counter = [0]
    
    try:
        # 建立 Realtime 连接
        event_queue = await realtime_service.connect(loop)
        
        # 设置系统提示词
        system_prompt = get_interaction_system_prompt(user_profile)
        await realtime_service.send_system_prompt(system_prompt, loop)
        
        # 发送连接成功消息
        await websocket.send_json({
            "type": "connected",
            "message": "Realtime 连接成功"
        })
        
        # 触发 AI 初始问候
        greeting_instruction = """You are a friendly English tutor starting a conversation.
Say a warm, casual greeting and ask the user what they'd like to practice or talk about today.
Keep it short and natural, like "Hey there! What would you like to chat about today?" 
Speak in English only."""
        await realtime_service.trigger_initial_greeting(greeting_instruction, loop)
        
        # 启动心跳任务 - 定期发送静音音频保持连接
        keep_alive_running = True
        async def keep_alive():
            """每5秒发送一小段静音音频，防止服务端超时"""
            # 200ms 的静音 PCM 数据 (16kHz, mono, 16bit)
            silence_samples = 3200  # 200ms * 16000Hz = 3200 samples
            silence_audio = bytes(silence_samples * 2)  # 16bit = 2 bytes per sample
            
            while keep_alive_running:
                try:
                    await asyncio.sleep(5)
                    if keep_alive_running and realtime_service.is_connected:
                        await realtime_service.send_audio(silence_audio, loop)
                        logger.debug("[Realtime] 发送心跳静音")
                except Exception as e:
                    logger.debug(f"[Realtime] 心跳发送失败: {e}")
                    break
        
        keep_alive_task = asyncio.create_task(keep_alive())
        
        # 启动事件处理任务
        async def process_realtime_events():
            """处理来自 Realtime API 的事件"""
            nonlocal full_response_text, current_transcription
            
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
                
                event_type = event.get("type")
                data = event.get("data", {})
                
                try:
                    if event_type == "session_created":
                        await websocket.send_json({
                            "type": "session_created",
                            "session_id": data.get("session_id")
                        })
                    
                    elif event_type == "transcription":
                        current_transcription = data.get("text", "")
                        await websocket.send_json({
                            "type": "transcription",
                            "text": current_transcription
                        })
                    
                    elif event_type == "text_delta":
                        delta = data.get("delta", "")
                        full_response_text += delta
                        await websocket.send_json({
                            "type": "text_delta",
                            "delta": delta
                        })
                    
                    elif event_type == "audio_delta":
                        await websocket.send_json({
                            "type": "audio_delta",
                            "audio": data.get("audio", "")
                        })
                    
                    elif event_type == "speech_started":
                        # 用户开始说话，清空之前的缓冲
                        audio_buffer.clear()
                        await websocket.send_json({"type": "speech_started"})
                    
                    elif event_type == "speech_stopped":
                        await websocket.send_json({"type": "speech_stopped"})
                    
                    elif event_type == "response_done":
                        await websocket.send_json({"type": "response_done"})
                        
                        # 响应完成，启动翻译和评估
                        if full_response_text:
                            # 异步翻译
                            asyncio.create_task(
                                run_translation(full_response_text, user_profile, websocket, processor, loop)
                            )
                        
                        if current_transcription and audio_buffer:
                            # 异步评估
                            eval_order_counter[0] += 1
                            order = eval_order_counter[0]
                            audio_data = b''.join(audio_buffer)
                            recent_user_transcriptions.append(current_transcription)
                            if EVALUATION_AGGREGATE_TURNS > 0:
                                recent_user_transcriptions = recent_user_transcriptions[-EVALUATION_AGGREGATE_TURNS:]
                            aggregated_transcription = " ".join([t for t in recent_user_transcriptions if t]).strip()
                            asyncio.create_task(
                                run_evaluation(
                                    audio_data, current_transcription, aggregated_transcription, order,
                                    eval_semaphore, websocket, processor, loop,
                                    user_id, user_repo, user_profile, conversation_id
                                )
                            )
                        
                        # 重置
                        full_response_text = ""
                        current_transcription = ""
                    
                    elif event_type == "error":
                        await websocket.send_json({
                            "type": "error",
                            "message": data.get("message", "Unknown error")
                        })
                    
                    elif event_type == "disconnected":
                        logger.info("[Realtime] 收到断开事件")
                        break
                        
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"[Realtime] 事件处理错误: {e}")
        
        # 启动事件处理
        event_task = asyncio.create_task(process_realtime_events())
        
        # 处理客户端消息
        while True:
            try:
                message = await websocket.receive()
                
                if message["type"] == "websocket.disconnect":
                    break
                
                if "bytes" in message:
                    # 直接接收二进制音频数据
                    audio_data = message["bytes"]
                    audio_buffer.append(audio_data)
                    await realtime_service.send_audio(audio_data, loop)
                
                elif "text" in message:
                    import json
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "audio":
                        # Base64 编码的音频
                        audio_b64 = data.get("data", "")
                        audio_data = base64.b64decode(audio_b64)
                        audio_buffer.append(audio_data)
                        await realtime_service.send_audio(audio_data, loop)
                    
                    elif msg_type == "interrupt":
                        await realtime_service.interrupt(loop)
                        await websocket.send_json({"type": "interrupted"})
                    
                    elif msg_type == "end":
                        break
                        
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[Realtime] 消息处理错误: {e}")
                break
        
        # 取消事件处理任务
        event_task.cancel()
        
    except Exception as e:
        logger.error(f"[Realtime] 错误: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    
    finally:
        # 停止心跳任务
        keep_alive_running = False
        if 'keep_alive_task' in dir():
            keep_alive_task.cancel()
        
        # 断开 Realtime 连接
        await realtime_service.disconnect(loop)
        logger.info("[Realtime] WebSocket 连接关闭")


async def run_translation(
    english_text: str,
    user_profile: dict,
    websocket: WebSocket,
    processor: UnifiedProcessor,
    loop: asyncio.AbstractEventLoop
):
    """异步执行翻译"""
    try:
        user_level = user_profile.get('cefr_level', 'A1')
        
        # 调用翻译
        translation = await loop.run_in_executor(
            None,
            lambda: processor.translate_text(english_text, user_level)
        )
        
        if translation:
            await websocket.send_json({
                "type": "translation",
                "text": translation
            })
            logger.info(f"[Realtime] 翻译完成: {translation[:50]}...")
    except Exception as e:
        logger.error(f"[Realtime] 翻译错误: {e}")


async def run_evaluation(
    audio_data: bytes,
    transcription: str,
    aggregated_transcription: str,
    order: int,
    semaphore: asyncio.Semaphore,
    websocket: WebSocket,
    processor: UnifiedProcessor,
    loop: asyncio.AbstractEventLoop,
    user_id: Optional[str],
    user_repo,
    user_profile: dict,
    conversation_id: Optional[str]
):
    """异步执行评估"""
    try:
        # 评分节奏控制：非指定轮次跳过评估
        if EVALUATION_CADENCE_TURNS > 1 and (order % EVALUATION_CADENCE_TURNS) != 0:
            logger.info(f"[Realtime] 评估节奏跳过: order={order}")
            return

        # 尝试获取信号量
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            logger.warning(f"[Realtime] 评估队列已满，跳过 order={order}")
            return
        
        try:
            # 执行评估（综合最近 N 轮转录）
            if aggregated_transcription:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: processor.evaluate_only(
                            transcription=aggregated_transcription,
                            conversation_history=None,
                            user_profile=user_profile
                        )
                    ),
                    timeout=60
                )
            else:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: processor.evaluate_audio_no_context(
                            audio_data=audio_data,
                            audio_format="pcm"
                        )
                    ),
                    timeout=60
                )
            
            if result and result.evaluation:
                eval_data = {
                    "transcription": aggregated_transcription or result.transcription or transcription,
                    "overall_score": result.evaluation.get("overall_score", 0),
                    "cefr_level": result.evaluation.get("cefr_level", "A1"),
                    "prosody_feedback": result.evaluation.get("prosody_feedback", ""),
                    "encouragement": result.evaluation.get("encouragement", ""),
                    "corrections": result.evaluation.get("corrections", []),
                    "good_expressions": result.evaluation.get("good_expressions", []),
                    "order": order
                }
                
                await websocket.send_json({
                    "type": "evaluation",
                    "data": eval_data
                })
                logger.info(f"[Realtime] 评估完成: order={order}, score={eval_data['overall_score']}")
                
                # 更新用户画像
                if user_id and user_repo:
                    try:
                        new_score = eval_data["overall_score"]
                        old_score = user_profile.get("average_score", 50)
                        updated_score = old_score * 0.7 + new_score * 0.3
                        
                        user_repo.update_profile(user_id, {
                            "average_score": updated_score,
                            "cefr_level": eval_data["cefr_level"],
                            "updated_at": datetime.utcnow().isoformat()
                        })
                    except Exception as e:
                        logger.error(f"[Realtime] 更新用户画像失败: {e}")
                        
        finally:
            semaphore.release()
            
    except asyncio.TimeoutError:
        logger.warning(f"[Realtime] 评估超时: order={order}")
    except Exception as e:
        logger.error(f"[Realtime] 评估错误: {e}")

