"""
完整语音对话API端点 - 语音输入 → 语音输出
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from typing import Optional
import io

from services.speech import SpeechService, SpeechServiceFactory
from services.tts import TTSService, TTSServiceFactory
from core.conversation import ConversationManager
from services.utils.text_processor import normalize_mixed_text, detect_language_mix
from config.settings import Settings
from services.utils.logger import get_logger

router = APIRouter(prefix="/voice-chat", tags=["voice-conversation"])

logger = get_logger("api.voice_conversation")
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


@router.post("/start")
async def start_voice_conversation(
    user_id: str = Query(..., description="用户ID"),
    return_audio: bool = Query(True, description="是否返回语音"),
    tts_service: TTSService = Depends(get_tts_service),
    manager: ConversationManager = Depends(get_conversation_manager)
):
    """
    开始语音对话
    
    返回:
    - conversation_id: 对话ID
    - initial_question: 初始问题文本
    - audio: 初始问题语音 (可选)
    """
    try:
        conversation = manager.start_conversation(user_id)
        initial_question = conversation.messages[-1].content if conversation.messages else ""
        
        response_data = {
            "conversation_id": conversation.conversation_id,
            "initial_question": initial_question,
            "user_profile": manager.get_user_profile(user_id).dict() if manager.get_user_profile(user_id) else {}
        }
        
        # 如果需要语音，转换初始问题为语音
        if return_audio and initial_question:
            audio_data = await tts_service._text_to_speech_async(
                text=initial_question,
                voice=getattr(settings, 'tts_default_voice', None)
            )
            # 返回JSON + audio_base64
            import base64
            response_data["audio_base64"] = base64.b64encode(audio_data).decode('utf-8')
            response_data["audio_format"] = "mp3"
        
        return response_data
        
    except Exception as e:
        logger.error(f"开始语音对话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conversation_id}/speak")
async def voice_respond(
    conversation_id: str,
    audio_file: UploadFile = File(..., description="用户语音文件"),
    return_audio: bool = Query(True, description="是否返回语音回复"),
    speech_service: SpeechService = Depends(get_speech_service),
    tts_service: TTSService = Depends(get_tts_service),
    manager: ConversationManager = Depends(get_conversation_manager)
):
    """
    语音对话 - 完整流程
    
    流程:
    1. 接收用户语音 → STT转文字
    2. LLM处理 + 评估
    3. 更新用户画像 (存入数据库)
    4. 生成下一个问题 (基于历史+画像+兴趣)
    5. TTS转语音返回 (可选)
    
    输入: 用户语音文件 (mp3/wav/webm等)
    输出: 评估结果 + 下一个问题 + 语音回复
    """
    # 检查文件类型
    allowed_types = ["audio/mpeg", "audio/mp4", "audio/wav", "audio/webm", "audio/m4a", "audio/x-wav"]
    content_type = audio_file.content_type or ""
    
    # 宽松检查
    if not any(t in content_type for t in ["audio", "mpeg", "wav", "webm"]):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的音频格式: {content_type}"
        )
    
    try:
        # ===== 1. STT: 语音转文字 =====
        audio_data = await audio_file.read()
        if not audio_data:
            raise HTTPException(status_code=400, detail="音频文件为空")
        
        audio_io = io.BytesIO(audio_data)
        transcribed_text = speech_service.transcribe_audio(audio_io)
        
        if not transcribed_text or not transcribed_text.strip():
            raise HTTPException(status_code=400, detail="无法识别语音内容")
        
        # 处理中英文混杂
        language_analysis = detect_language_mix(transcribed_text)
        normalized_text = normalize_mixed_text(transcribed_text)
        
        logger.info(f"[语音识别] 原文: {transcribed_text}, 规范化: {normalized_text}")
        
        # ===== 2-4. 处理回答 + 评估 + 生成下一问题 =====
        conversation, assessment_result, next_question = manager.process_user_response(
            conversation_id=conversation_id,
            user_response=normalized_text
        )
        
        # 获取更新后的用户画像 (已存入数据库)
        user_profile = manager.get_user_profile(conversation.user_id)
        round_number = len([m for m in conversation.messages if m.role.value == "user"])
        
        # 构建响应
        response_data = {
            "round_number": round_number,
            "transcribed_text": transcribed_text,
            "normalized_text": normalized_text,
            "language_analysis": language_analysis,
            "next_question": next_question,
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
            "conversation_state": conversation.state.value
        }
        
        # ===== 5. TTS: 下一个问题转语音 =====
        if return_audio and next_question:
            try:
                audio_response = await tts_service._text_to_speech_async(
                    text=next_question,
                    voice=getattr(settings, 'tts_default_voice', None)
                )
                import base64
                response_data["audio_base64"] = base64.b64encode(audio_response).decode('utf-8')
                response_data["audio_format"] = "mp3"
            except Exception as tts_error:
                logger.warning(f"TTS转换失败，仅返回文本: {tts_error}")
                response_data["audio_error"] = str(tts_error)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"语音对话处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.post("/{conversation_id}/speak-stream")
async def voice_respond_stream(
    conversation_id: str,
    audio_file: UploadFile = File(..., description="用户语音文件"),
    speech_service: SpeechService = Depends(get_speech_service),
    tts_service: TTSService = Depends(get_tts_service),
    manager: ConversationManager = Depends(get_conversation_manager)
):
    """
    语音对话 - 直接返回语音流
    
    输入: 用户语音文件
    输出: 下一个问题的语音流 (audio/mpeg)
    
    响应头包含评估信息:
    - X-Round-Number
    - X-Transcribed-Text
    - X-Overall-Score
    - X-CEFR-Level
    """
    allowed_types = ["audio/mpeg", "audio/mp4", "audio/wav", "audio/webm", "audio/m4a"]
    
    try:
        # 1. STT
        audio_data = await audio_file.read()
        audio_io = io.BytesIO(audio_data)
        transcribed_text = speech_service.transcribe_audio(audio_io)
        
        if not transcribed_text:
            raise HTTPException(status_code=400, detail="无法识别语音")
        
        normalized_text = normalize_mixed_text(transcribed_text)
        
        # 2-4. 处理
        conversation, assessment_result, next_question = manager.process_user_response(
            conversation_id=conversation_id,
            user_response=normalized_text
        )
        
        round_number = len([m for m in conversation.messages if m.role.value == "user"])
        
        # 5. TTS
        audio_response = await tts_service._text_to_speech_async(
            text=next_question,
            voice=getattr(settings, 'tts_default_voice', None)
        )
        
        # 返回语音流，评估信息放在响应头
        headers = {
            "X-Round-Number": str(round_number),
            "X-Transcribed-Text": transcribed_text[:100],  # 截断防止头过长
            "X-Overall-Score": str(assessment_result.overall_score),
            "X-CEFR-Level": assessment_result.cefr_level.value,
            "X-Next-Question": next_question[:200]
        }
        
        return StreamingResponse(
            io.BytesIO(audio_response),
            media_type="audio/mpeg",
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"语音流处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conversation_id}/end")
async def end_voice_conversation(
    conversation_id: str,
    return_audio: bool = Query(False, description="是否将报告转为语音"),
    tts_service: TTSService = Depends(get_tts_service),
    manager: ConversationManager = Depends(get_conversation_manager)
):
    """
    结束语音对话，获取最终报告
    
    返回:
    - 最终总分
    - CEFR等级
    - 优势列表
    - 弱点列表
    - 学习建议
    - 完整报告 (可选语音版)
    """
    try:
        report = manager.end_conversation(conversation_id)
        
        response_data = {
            "conversation_id": conversation_id,
            "status": "completed",
            "report": report,
            "message": "对话已结束，学习报告已生成"
        }
        
        # 如果需要语音报告
        if return_audio and report:
            # 生成报告摘要
            summary_text = f"""
            Your English conversation session has ended. 
            Your overall score is {report.get('overall_score', 'N/A')} points, 
            reaching CEFR level {report.get('cefr_level', 'N/A')}.
            Your main strengths are: {', '.join(report.get('strengths', [])[:3])}.
            Areas to improve: {', '.join(report.get('weaknesses', [])[:3])}.
            Keep practicing and you'll continue to improve!
            """
            
            try:
                audio_data = await tts_service._text_to_speech_async(
                    text=summary_text.strip(),
                    voice=getattr(settings, 'tts_default_voice', None)
                )
                import base64
                response_data["report_audio_base64"] = base64.b64encode(audio_data).decode('utf-8')
                response_data["audio_format"] = "mp3"
            except Exception as tts_error:
                logger.warning(f"报告TTS转换失败: {tts_error}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"结束对话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

