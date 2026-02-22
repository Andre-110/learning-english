"""
语音输入API端点
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import Optional
import io

from services.speech import SpeechService, SpeechServiceFactory
from services.llm import LLMServiceFactory, LLMProvider
from core.conversation import ConversationManager
from utils.text_processor import normalize_mixed_text, detect_language_mix
from config.settings import Settings
from config.llm_config import llm_config

router = APIRouter(prefix="/conversations", tags=["speech"])

settings = Settings()


def get_speech_service() -> SpeechService:
    """获取语音服务（使用全局配置）"""
    from config.settings import Settings
    from services.utils.logger import get_logger
    
    logger = get_logger("api.speech_endpoint")
    settings = Settings()
    
    logger.info(f"创建语音服务: provider={settings.speech_provider}")
    
    if settings.speech_provider == "funasr":
        logger.info(f"使用FunASR: model={settings.funasr_model_name}, language={settings.funasr_language}")
        return SpeechServiceFactory.create(
            provider="funasr",
            model_dir=settings.funasr_model_dir,
            model_name=settings.funasr_model_name,
            language=settings.funasr_language
        )
    else:
        logger.info("使用Whisper API")
        return SpeechServiceFactory.create(provider="whisper")


def get_conversation_manager() -> ConversationManager:
    """获取对话管理器（复用主应用的逻辑）"""
    from api.main import get_conversation_manager
    return get_conversation_manager()


@router.post("/{conversation_id}/respond-audio")
async def respond_with_audio(
    conversation_id: str,
    audio_file: UploadFile = File(...),
    speech_service: SpeechService = Depends(get_speech_service),
    manager: ConversationManager = Depends(get_conversation_manager)
):
    """
    通过语音输入回答问题
    
    支持的音频格式：mp3, mp4, mpeg, mpga, m4a, wav, webm
    """
    # 检查文件类型
    allowed_types = ["audio/mpeg", "audio/mp4", "audio/wav", "audio/webm", "audio/m4a"]
    if audio_file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的音频格式: {audio_file.content_type}"
        )
    
    try:
        # 1. 读取音频文件
        audio_data = await audio_file.read()
        
        # 检查文件是否为空
        if not audio_data or len(audio_data) == 0:
            raise HTTPException(
                status_code=400,
                detail="音频文件为空或无法读取"
            )
        
        audio_io = io.BytesIO(audio_data)
        
        # 2. 语音转文本
        transcribed_text = speech_service.transcribe_audio(audio_io)
        
        if not transcribed_text or not transcribed_text.strip():
            raise HTTPException(
                status_code=400,
                detail="音频转录失败，无法识别语音内容"
            )
        
        # 3. 处理中英文混杂
        language_analysis = detect_language_mix(transcribed_text)
        normalized_text = normalize_mixed_text(transcribed_text)
        
        # 4. 进入正常处理流程
        conversation, assessment_result, next_question = manager.process_user_response(
            conversation_id=conversation_id,
            user_response=normalized_text
        )
        
        # 5. 获取用户画像
        user_profile = manager.get_user_profile(conversation.user_id)
        
        round_number = len([m for m in conversation.messages if m.role.value == "user"])
        
        return {
            "transcribed_text": transcribed_text,
            "normalized_text": normalized_text,
            "language_analysis": language_analysis,
            "next_question": next_question,
            "assessment": assessment_result.dict(),
            "user_profile": user_profile.dict() if user_profile else {},
            "round_number": round_number
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理语音输入失败: {str(e)}")

