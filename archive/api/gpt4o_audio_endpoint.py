"""
GPT-4o Audio WebSocket端点 - 使用GPT-4o直接处理音频

这是一个新的链路，直接将音频发送给GPT-4o Audio模型，
无需先进行STT转录，可以减少延迟并保留语音细节。

链路对比：
- 原链路: 音频 → FunASR(STT) → 文本 → GPT-4 → 文本 → TTS → 音频
- 新链路: 音频 → GPT-4o Audio → 文本 → TTS → 音频
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional
from datetime import datetime
import json
import base64
import io
import asyncio

from services.gpt4o_audio import GPT4oAudioService, create_gpt4o_audio_service
from services.tts import TTSService, TTSServiceFactory
from core.conversation import ConversationManager
from models.conversation import MessageRole
from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("api.gpt4o_audio")
router = APIRouter(prefix="/gpt4o-audio", tags=["gpt4o-audio"])

settings = Settings()


def get_gpt4o_audio_service() -> GPT4oAudioService:
    """获取GPT-4o Audio服务"""
    return create_gpt4o_audio_service(
        model="gpt-4o-audio-preview"  # 或者通过配置指定
    )


def get_tts_service() -> TTSService:
    """获取TTS服务"""
    provider = settings.tts_provider
    
    if provider == "edge-tts":
        return TTSServiceFactory.create(
            provider="edge-tts",
            default_voice=getattr(settings, 'tts_default_voice', 'en-US-JennyNeural')
        )
    else:
        return TTSServiceFactory.create(
            provider=provider,
            model=getattr(settings, 'tts_model', 'gpt-4o-mini-tts'),
            default_voice=getattr(settings, 'tts_default_voice', 'alloy')
        )


@router.websocket("/{conversation_id}/chat")
async def gpt4o_audio_chat(
    websocket: WebSocket,
    conversation_id: str
):
    """
    GPT-4o Audio WebSocket端点
    
    消息格式：
    客户端 → 服务端:
    - {"type": "start"} - 开始录音
    - {"type": "audio_data", "data": "base64_audio"} - 音频数据
    - {"type": "audio_end"} - 音频结束，开始处理
    
    服务端 → 客户端:
    - {"type": "connected"} - 连接成功
    - {"type": "processing", "stage": "..."} - 处理阶段
    - {"type": "transcription", "text": "..."} - 转录结果
    - {"type": "evaluation", "data": {...}} - 评估结果
    - {"type": "response", "text": "..."} - AI响应/问题
    - {"type": "audio_chunk", "data": "..."} - TTS音频块
    - {"type": "audio_end"} - 音频结束
    - {"type": "error", "message": "..."} - 错误
    """
    await websocket.accept()
    
    # 初始化服务
    gpt4o_service = get_gpt4o_audio_service()
    tts_service = get_tts_service()
    
    # 获取对话管理器
    from api.main import get_conversation_manager
    manager = get_conversation_manager()
    
    # 验证对话存在
    conversation = manager.conversation_repo.get(conversation_id)
    if not conversation:
        await websocket.send_json({
            "type": "error",
            "message": f"对话 {conversation_id} 不存在"
        })
        await websocket.close()
        return
    
    # 获取用户画像
    user_profile = manager.user_repo.get(conversation.user_id)
    user_profile_dict = user_profile.dict() if user_profile else None
    
    await websocket.send_json({
        "type": "connected",
        "conversation_id": conversation_id,
        "mode": "gpt4o-audio",
        "message": "已连接到GPT-4o Audio服务（直接音频处理模式）"
    })
    
    # 音频缓冲区
    audio_buffer = []
    is_recording = False
    
    # 对话历史（用于GPT-4o）
    conversation_history = []
    
    # 从现有对话中提取历史
    for msg in conversation.messages[-6:]:  # 最近3轮
        if msg.role == MessageRole.USER:
            conversation_history.append({
                "role": "user",
                "content": [{"type": "text", "text": msg.content}]
            })
        elif msg.role == MessageRole.ASSISTANT:
            conversation_history.append({
                "role": "assistant",
                "content": msg.content
            })
    
    try:
        while True:
            message = await websocket.receive()
            
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "start":
                        # 开始录音
                        is_recording = True
                        audio_buffer = []
                        await websocket.send_json({
                            "type": "recording_started",
                            "message": "开始录音（GPT-4o Audio模式）"
                        })
                    
                    elif msg_type == "audio_data":
                        # 接收音频数据
                        if is_recording:
                            audio_chunk = base64.b64decode(data.get("data", ""))
                            audio_buffer.append(audio_chunk)
                    
                    elif msg_type == "audio_end":
                        # 音频结束，开始处理
                        if audio_buffer and is_recording:
                            is_recording = False
                            
                            # 使用流式处理
                            await process_audio_with_gpt4o_stream(
                                websocket=websocket,
                                audio_buffer=audio_buffer,
                                gpt4o_service=gpt4o_service,
                                tts_service=tts_service,
                                conversation=conversation,
                                conversation_history=conversation_history,
                                user_profile_dict=user_profile_dict,
                                manager=manager
                            )
                            
                            audio_buffer = []
                    
                    elif msg_type == "close":
                        await websocket.close()
                        break
                        
                except json.JSONDecodeError:
                    pass
            
            elif "bytes" in message:
                # 二进制音频数据
                if is_recording:
                    audio_buffer.append(message["bytes"])
    
    except WebSocketDisconnect:
        logger.info(f"GPT-4o Audio WebSocket断开: {conversation_id}")
    except Exception as e:
        logger.error(f"GPT-4o Audio WebSocket错误: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass


async def process_audio_with_gpt4o(
    websocket: WebSocket,
    audio_buffer: list,
    gpt4o_service: GPT4oAudioService,
    tts_service: TTSService,
    conversation,
    conversation_history: list,
    user_profile_dict: Optional[dict],
    manager: ConversationManager
):
    """
    使用GPT-4o Audio处理音频
    
    这个函数实现了新的处理链路：
    音频 → GPT-4o Audio（转录+评估+生成问题） → TTS → 音频
    """
    import time
    start_time = time.time()
    
    try:
        # 1. 合并音频数据
        audio_data = b''.join(audio_buffer)
        if not audio_data:
            await websocket.send_json({
                "type": "error",
                "message": "音频数据为空"
            })
            return
        
        logger.info(f"[GPT-4o Audio] 收到音频: {len(audio_data)} bytes")
        
        # 2. 发送处理状态
        await websocket.send_json({
            "type": "processing",
            "stage": "gpt4o_audio",
            "message": "正在使用GPT-4o处理音频..."
        })
        
        # 3. 调用GPT-4o Audio（一次调用完成转录+评估+生成问题）
        gpt4o_start = time.time()
        
        result = gpt4o_service.process_audio_with_evaluation(
            audio_data=audio_data,
            audio_format="webm",  # 前端通常发送webm格式
            conversation_history=conversation_history,
            user_profile=user_profile_dict
        )
        
        gpt4o_time = time.time() - gpt4o_start
        logger.info(f"[GPT-4o Audio] 处理完成，耗时: {gpt4o_time*1000:.0f}ms")
        
        # 4. 发送转录结果
        transcription = result.get("transcription", "")
        if transcription:
            await websocket.send_json({
                "type": "transcription",
                "text": transcription,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            
            # 添加用户消息到对话
            conversation.add_message(MessageRole.USER, transcription)
        
        # 5. 发送评估结果
        evaluation = result.get("evaluation", {})
        if evaluation:
            await websocket.send_json({
                "type": "evaluation",
                "data": {
                    "assessment": {
                        "overall_score": evaluation.get("overall_score", 50),
                        "cefr_level": evaluation.get("cefr_level", "A2"),
                        "strengths": evaluation.get("strengths", []),
                        "weaknesses": evaluation.get("weaknesses", []),
                        "feedback": evaluation.get("feedback", ""),
                        "is_gpt4o_audio": True
                    },
                    "user_profile": user_profile_dict or {}
                }
            })
        
        # 6. 发送下一个问题
        next_question = result.get("next_question", "")
        if next_question:
            await websocket.send_json({
                "type": "response",
                "text": next_question,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            
            # 添加助手消息到对话
            conversation.add_message(MessageRole.ASSISTANT, next_question)
        
        # 7. 保存对话
        manager.conversation_repo.save(conversation)
        
        # 8. 生成TTS音频
        if next_question:
            await stream_tts_audio(
                websocket=websocket,
                tts_service=tts_service,
                text=next_question
            )
        
        # 9. 记录总耗时
        total_time = time.time() - start_time
        logger.info(f"[GPT-4o Audio] 总处理时间: {total_time*1000:.0f}ms")
        
        await websocket.send_json({
            "type": "stats",
            "data": {
                "gpt4o_time_ms": int(gpt4o_time * 1000),
                "total_time_ms": int(total_time * 1000),
                "mode": "gpt4o-audio"
            }
        })
        
    except Exception as e:
        logger.error(f"[GPT-4o Audio] 处理错误: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "message": f"处理失败: {str(e)}"
        })


async def process_audio_with_gpt4o_stream(
    websocket: WebSocket,
    audio_buffer: list,
    gpt4o_service: GPT4oAudioService,
    tts_service: TTSService,
    conversation,
    conversation_history: list,
    user_profile_dict: Optional[dict],
    manager: ConversationManager
):
    """
    使用GPT-4o Audio流式处理音频
    
    流式链路：
    音频 → GPT-4o Audio（流式输出） → 边生成边发送文本 → TTS → 音频
    
    优势：
    - 首字延迟更低（不用等待完整响应）
    - 用户可以看到逐字生成的效果
    """
    import time
    start_time = time.time()
    first_chunk_time = None
    
    try:
        # 1. 合并音频数据
        audio_data = b''.join(audio_buffer)
        if not audio_data:
            await websocket.send_json({
                "type": "error",
                "message": "音频数据为空"
            })
            return
        
        logger.info(f"[GPT-4o Audio Stream] 收到音频: {len(audio_data)} bytes")
        
        # 2. 发送处理状态
        await websocket.send_json({
            "type": "processing",
            "stage": "gpt4o_audio_stream",
            "message": "正在使用GPT-4o流式处理音频..."
        })
        
        # 3. 流式调用GPT-4o Audio
        gpt4o_start = time.time()
        full_response = ""
        parsed_data = None
        
        import asyncio
        import queue
        import threading
        
        # 使用队列实现真正的流式传输
        result_queue = queue.Queue()
        stream_done = threading.Event()
        
        def run_stream_producer():
            """在线程中运行同步生成器，将结果放入队列"""
            try:
                for item in gpt4o_service.process_audio_with_evaluation_stream(
                    audio_data=audio_data,
                    audio_format="webm",
                    conversation_history=conversation_history,
                    user_profile=user_profile_dict
                ):
                    result_queue.put(item)
            except Exception as e:
                result_queue.put({"type": "error", "message": str(e)})
            finally:
                stream_done.set()
        
        # 启动生产者线程
        producer_thread = threading.Thread(target=run_stream_producer)
        producer_thread.start()
        
        # 异步消费队列中的结果
        while not stream_done.is_set() or not result_queue.empty():
            try:
                # 非阻塞获取，超时10ms
                item = result_queue.get(timeout=0.01)
            except queue.Empty:
                await asyncio.sleep(0.005)  # 让出控制权
                continue
            
            if item["type"] == "chunk":
                content = item["content"]
                full_response += content
                
                # 记录首字时间
                if first_chunk_time is None:
                    first_chunk_time = time.time()
                    first_chunk_latency = (first_chunk_time - gpt4o_start) * 1000
                    logger.info(f"[GPT-4o Audio Stream] 首字延迟: {first_chunk_latency:.0f}ms")
                
                # 立即发送文本片段给前端
                await websocket.send_json({
                    "type": "response_chunk",
                    "content": content
                })
                
            elif item["type"] == "complete":
                parsed_data = item["data"]
            
            elif item["type"] == "error":
                raise Exception(item["message"])
        
        # 等待生产者线程结束
        producer_thread.join(timeout=5.0)
        
        gpt4o_time = time.time() - gpt4o_start
        logger.info(f"[GPT-4o Audio Stream] 流式处理完成，总耗时: {gpt4o_time*1000:.0f}ms")
        
        # 4. 发送转录结果
        if parsed_data:
            transcription = parsed_data.get("transcription", "")
            if transcription:
                await websocket.send_json({
                    "type": "transcription",
                    "text": transcription,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                conversation.add_message(MessageRole.USER, transcription)
            
            # 5. 发送评估结果
            evaluation = parsed_data.get("evaluation", {})
            if evaluation:
                await websocket.send_json({
                    "type": "evaluation",
                    "data": {
                        "assessment": {
                            "overall_score": evaluation.get("overall_score", 50),
                            "cefr_level": evaluation.get("cefr_level", "A2"),
                            "strengths": evaluation.get("strengths", []),
                            "weaknesses": evaluation.get("weaknesses", []),
                            "feedback": evaluation.get("feedback", ""),
                            "is_gpt4o_audio": True,
                            "is_streaming": True
                        },
                        "user_profile": user_profile_dict or {}
                    }
                })
            
            # 6. 发送完整响应结束标记
            next_question = parsed_data.get("next_question", "")
            if next_question:
                await websocket.send_json({
                    "type": "response_complete",
                    "text": next_question,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                conversation.add_message(MessageRole.ASSISTANT, next_question)
        
        # 7. 保存对话
        manager.conversation_repo.save(conversation)
        
        # 8. 生成TTS音频
        if parsed_data and parsed_data.get("next_question"):
            await stream_tts_audio(
                websocket=websocket,
                tts_service=tts_service,
                text=parsed_data["next_question"]
            )
        
        # 9. 记录统计
        total_time = time.time() - start_time
        logger.info(f"[GPT-4o Audio Stream] 总处理时间: {total_time*1000:.0f}ms")
        
        await websocket.send_json({
            "type": "stats",
            "data": {
                "gpt4o_time_ms": int(gpt4o_time * 1000),
                "first_chunk_ms": int((first_chunk_time - gpt4o_start) * 1000) if first_chunk_time else None,
                "total_time_ms": int(total_time * 1000),
                "mode": "gpt4o-audio-stream"
            }
        })
        
    except Exception as e:
        logger.error(f"[GPT-4o Audio Stream] 处理错误: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "message": f"流式处理失败: {str(e)}"
        })


async def stream_tts_audio(
    websocket: WebSocket,
    tts_service: TTSService,
    text: str
):
    """流式生成TTS音频"""
    try:
        from services.tts import EdgeTTSService, OpenAITTSService
        import time
        
        start_time = time.time()
        
        if isinstance(tts_service, EdgeTTSService):
            # Edge TTS 流式生成
            import edge_tts
            voice = tts_service.default_voice or 'en-US-JennyNeural'
            communicate = edge_tts.Communicate(text, voice)
            
            chunk_count = 0
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    await websocket.send_json({
                        "type": "audio_chunk",
                        "data": base64.b64encode(chunk["data"]).decode('utf-8')
                    })
                    chunk_count += 1
            
            logger.info(f"[TTS] Edge TTS完成: {chunk_count}块, 耗时: {(time.time()-start_time)*1000:.0f}ms")
        
        else:
            # OpenAI TTS
            audio_data = await tts_service._text_to_speech_async(
                text=text,
                voice=getattr(settings, 'tts_default_voice', 'alloy')
            )
            
            # 分块发送
            chunk_size = 8 * 1024
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                await websocket.send_json({
                    "type": "audio_chunk",
                    "data": base64.b64encode(chunk).decode('utf-8')
                })
                await asyncio.sleep(0.005)
            
            logger.info(f"[TTS] OpenAI TTS完成: {len(audio_data)}字节, 耗时: {(time.time()-start_time)*1000:.0f}ms")
        
        # 发送结束标记
        await websocket.send_json({
            "type": "audio_end",
            "message": "语音生成完成"
        })
        
    except Exception as e:
        logger.error(f"[TTS] 生成错误: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "message": f"语音生成失败: {str(e)}"
        })

