"""
流式语音对话WebSocket端点 - 支持实时音频输入输出
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Optional
import json
import base64
import io
import asyncio

from services.speech import SpeechService, SpeechServiceFactory
from services.tts import TTSService, TTSServiceFactory
from core.conversation import ConversationManager
from services.utils.text_processor import normalize_mixed_text, detect_language_mix
from config.settings import Settings
from services.utils.logger import get_logger

router = APIRouter(prefix="/voice-stream", tags=["voice-stream"])

logger = get_logger("api.voice_stream")
settings = Settings()


def get_speech_service() -> SpeechService:
    """获取STT语音服务"""
    if settings.speech_provider == "funasr":
        return SpeechServiceFactory.create(
            provider="funasr",
            model_dir=settings.funasr_model_dir,
            model_name=settings.funasr_model_name,
            language=settings.funasr_language
        )
    else:
        return SpeechServiceFactory.create(provider="whisper")


def get_tts_service() -> TTSService:
    """获取TTS语音服务"""
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


def get_conversation_manager() -> ConversationManager:
    """获取对话管理器"""
    from api.main import get_conversation_manager
    return get_conversation_manager()


@router.websocket("/{conversation_id}")
async def voice_stream_websocket(
    websocket: WebSocket,
    conversation_id: str
):
    """
    WebSocket流式语音对话端点
    
    消息格式：
    - 客户端 -> 服务端：
        - {"type": "audio", "data": "base64_encoded_audio"} - 发送音频数据
        - {"type": "end"} - 结束对话
    
    - 服务端 -> 客户端：
        - {"type": "connected"} - 连接成功
        - {"type": "transcription", "text": "..."} - 转录结果
        - {"type": "assessment", "data": {...}} - 评估结果
        - {"type": "audio", "data": "base64_encoded_audio", "format": "mp3"} - 音频回复
        - {"type": "error", "message": "..."} - 错误信息
    """
    await websocket.accept()
    
    speech_service = get_speech_service()
    tts_service = get_tts_service()
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
            "message": "已连接到流式语音服务",
            "conversation_id": conversation_id
        })
        
        while True:
            try:
                # 接收消息（可以是文本或二进制）
                data = await websocket.receive()
                
                if "text" in data:
                    # 文本消息（JSON控制消息）
                    message = json.loads(data["text"])
                    msg_type = message.get("type")
                    
                    if msg_type == "end":
                        # 结束对话
                        report = manager.end_conversation(conversation_id)
                        await websocket.send_json({
                            "type": "report",
                            "data": report
                        })
                        await websocket.close()
                        break
                    elif msg_type == "ping":
                        # 心跳消息
                        await websocket.send_json({"type": "pong"})
                
                elif "bytes" in data:
                    # 二进制音频数据
                    audio_data = data["bytes"]
                    await process_audio_chunk(
                        websocket,
                        audio_data,
                        speech_service,
                        tts_service,
                        manager,
                        conversation_id
                    )
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket连接断开: {conversation_id}")
                break
            
            except Exception as e:
                logger.error(f"处理WebSocket消息错误: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"处理失败: {str(e)}"
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
            await websocket.close()


async def process_audio_chunk(
    websocket: WebSocket,
    audio_data: bytes,
    speech_service: SpeechService,
    tts_service: TTSService,
    manager: ConversationManager,
    conversation_id: str
):
    """处理音频数据块"""
    try:
        # STT: 语音转文字
        audio_io = io.BytesIO(audio_data)
        transcribed_text = speech_service.transcribe_audio(audio_io)
        
        if not transcribed_text or not transcribed_text.strip():
            return
        
        # 处理中英文混杂
        language_analysis = detect_language_mix(transcribed_text)
        normalized_text = normalize_mixed_text(transcribed_text)
        
        logger.info(f"[语音识别] 原文: {transcribed_text}, 规范化: {normalized_text}")
        
        # 发送转录结果
        await websocket.send_json({
            "type": "transcription",
            "text": transcribed_text,
            "normalized_text": normalized_text,
            "language_analysis": language_analysis
        })
        
        # 处理用户回答 + 评估 + 生成下一问题
        conversation, assessment_result, next_question = manager.process_user_response(
            conversation_id=conversation_id,
            user_response=normalized_text
        )
        
        # 获取更新后的用户画像
        user_profile = manager.get_user_profile(conversation.user_id)
        round_number = len([m for m in conversation.messages if m.role.value == "user"])
        
        # 发送评估结果
        await websocket.send_json({
            "type": "assessment",
            "data": {
                "round_number": round_number,
                "assessment": {
                    "overall_score": assessment_result.overall_score,
                    "grammar_score": assessment_result.grammar_score,
                    "vocabulary_score": assessment_result.vocabulary_score,
                    "fluency_score": assessment_result.fluency_score,
                    "pronunciation_score": assessment_result.pronunciation_score,
                    "cefr_level": assessment_result.cefr_level.value,
                    "feedback": assessment_result.feedback,
                    "strengths": assessment_result.strengths,
                    "weaknesses": assessment_result.weaknesses
                },
                "user_profile": {
                    "user_id": user_profile.user_id,
                    "overall_score": user_profile.overall_score,
                    "cefr_level": user_profile.cefr_level.value,
                    "strengths": user_profile.strengths,
                    "weaknesses": user_profile.weaknesses,
                    "conversation_count": user_profile.conversation_count,
                    "interests": [i.dict() for i in user_profile.interests] if user_profile.interests else []
                } if user_profile else {},
                "next_question": next_question
            }
        })
        
        # TTS: 生成音频回复
        if next_question:
            try:
                audio_response = await tts_service._text_to_speech_async(
                    text=next_question,
                    voice=getattr(settings, 'tts_default_voice', None)
                )
                
                # 发送音频数据（base64编码）
                audio_base64 = base64.b64encode(audio_response).decode('utf-8')
                await websocket.send_json({
                    "type": "audio",
                    "data": audio_base64,
                    "format": "mp3",
                    "text": next_question
                })
            except Exception as tts_error:
                logger.warning(f"TTS转换失败: {tts_error}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"TTS转换失败: {str(tts_error)}"
                })
    
    except Exception as e:
        logger.error(f"处理音频块错误: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"处理音频失败: {str(e)}"
        })

