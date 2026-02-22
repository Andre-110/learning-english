"""
实时语音输入API端点 - WebSocket支持
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Optional
import json
import logging

from services.realtime_speech import RealtimeSpeechService, create_realtime_speech_service
from services.speech import SpeechServiceFactory
from services.utils.text_processor import normalize_mixed_text
from services.utils.logger import get_logger
from config.settings import Settings

logger = get_logger("api.realtime_speech")

router = APIRouter(prefix="/realtime-speech", tags=["realtime-speech"])


def get_conversation_manager():
    """获取对话管理器（复用主应用的逻辑）"""
    from api.main import get_conversation_manager as _get_conversation_manager
    return _get_conversation_manager()


@router.websocket("/{conversation_id}/listen")
async def websocket_realtime_speech(
    websocket: WebSocket,
    conversation_id: str
):
    """
    WebSocket实时语音输入端点
    
    消息格式：
    - 客户端 -> 服务端：
        - {"type": "start"} - 开始监听
        - {"type": "stop"} - 停止监听
        - {"type": "close"} - 关闭连接
    
    - 服务端 -> 客户端：
        - {"type": "connected"} - 连接成功
        - {"type": "listening_started"} - 监听已开始
        - {"type": "listening_stopped"} - 监听已停止
        - {"type": "transcription", "text": "..."} - 转录结果
        - {"type": "assessment", "data": {...}} - 评估结果
        - {"type": "error", "message": "..."} - 错误信息
    """
    await websocket.accept()
    
    # 从配置获取语音服务提供商
    settings = Settings()
    speech_provider = settings.speech_provider
    
    # 创建语音服务（根据配置选择whisper或funasr）
    if speech_provider == "funasr":
        speech_service = SpeechServiceFactory.create(
            provider="funasr",
            model_dir=settings.funasr_model_dir,
            model_name=settings.funasr_model_name,
            language=settings.funasr_language
        )
    else:
        # 默认使用whisper
        speech_service = SpeechServiceFactory.create(provider="whisper")
    
    logger.info(f"使用语音服务: {speech_provider}")
    realtime_service = create_realtime_speech_service(speech_service=speech_service)
    
    # 获取对话管理器
    manager = get_conversation_manager()
    
    # 验证对话是否存在
    conversation = manager.get_conversation(conversation_id)
    if not conversation:
        await websocket.send_json({
            "type": "error",
            "message": f"对话 {conversation_id} 不存在"
        })
        await websocket.close()
        return
    
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "已连接到实时语音服务",
            "conversation_id": conversation_id
        })
        
        def on_transcription(text: str):
            """转录回调函数"""
            import asyncio
            try:
                # 处理中英文混杂
                normalized_text = normalize_mixed_text(text)
                
                # 发送转录结果
                asyncio.create_task(websocket.send_json({
                    "type": "transcription",
                    "text": text,
                    "normalized_text": normalized_text
                }))
                
                # 处理用户回答
                try:
                    conversation, assessment_result, next_question = manager.process_user_response(
                        conversation_id=conversation_id,
                        user_response=normalized_text
                    )
                    
                    # 获取用户画像
                    user_profile = manager.get_user_profile(conversation.user_id)
                    
                    round_number = len([m for m in conversation.messages if m.role.value == "user"])
                    
                    # 发送评估结果
                    asyncio.create_task(websocket.send_json({
                        "type": "assessment",
                        "data": {
                            "assessment": assessment_result.dict(),
                            "user_profile": user_profile.dict() if user_profile else {},
                            "next_question": next_question,
                            "round_number": round_number
                        }
                    }))
                except Exception as e:
                    logger.error(f"处理用户回答错误: {e}")
                    asyncio.create_task(websocket.send_json({
                        "type": "error",
                        "message": f"处理用户回答失败: {str(e)}"
                    }))
            
            except Exception as e:
                logger.error(f"转录回调错误: {e}")
                asyncio.create_task(websocket.send_json({
                    "type": "error",
                    "message": f"处理转录结果失败: {str(e)}"
                }))
        
        # 监听WebSocket消息
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                msg_type = message.get("type")
                
                if msg_type == "start":
                    # 开始监听
                    realtime_service.start_listening(on_transcription=on_transcription)
                    await websocket.send_json({
                        "type": "listening_started",
                        "message": "已开始监听语音输入"
                    })
                
                elif msg_type == "stop":
                    # 停止监听
                    realtime_service.stop_listening()
                    await websocket.send_json({
                        "type": "listening_stopped",
                        "message": "已停止监听语音输入"
                    })
                
                elif msg_type == "close":
                    # 关闭连接
                    realtime_service.stop_listening()
                    await websocket.close()
                    break
            
            except WebSocketDisconnect:
                logger.info(f"WebSocket连接断开: {conversation_id}")
                realtime_service.stop_listening()
                break
            
            except Exception as e:
                logger.error(f"处理WebSocket消息错误: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"处理消息失败: {str(e)}"
                })
    
    except Exception as e:
        logger.error(f"WebSocket服务错误: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"服务错误: {str(e)}"
            })
        except:
            pass
        finally:
            realtime_service.stop_listening()
            await websocket.close()

