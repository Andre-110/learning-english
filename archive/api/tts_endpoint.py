"""
文本转语音（TTS）API端点
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict
import io

from services.tts import TTSService, TTSServiceFactory
from config.settings import Settings

router = APIRouter(prefix="/tts", tags=["tts"])

settings = Settings()


def get_tts_service() -> TTSService:
    """获取TTS服务"""
    from services.utils.logger import get_logger
    
    logger = get_logger("api.tts_endpoint")
    
    # 从配置中获取TTS提供商和参数
    tts_provider = getattr(settings, 'tts_provider', 'openai')
    tts_model = getattr(settings, 'tts_model', 'tts-1')
    default_voice = getattr(settings, 'tts_default_voice', None)
    
    logger.info(f"创建TTS服务: provider={tts_provider}, model={tts_model}, default_voice={default_voice}")
    
    if tts_provider == "openai":
        return TTSServiceFactory.create(
            provider="openai",
            model=tts_model,
            default_voice=default_voice
        )
    else:
        return TTSServiceFactory.create(
            provider="edge-tts",
            default_voice=default_voice
        )


@router.post("/text-to-speech")
async def text_to_speech(
    text: str = Query(..., description="要转换的文本"),
    voice: Optional[str] = Query(None, description="语音名称（如 'en-US-JennyNeural'）"),
    rate: Optional[str] = Query(None, description="语速（如 '+0%', '-50%'）"),
    volume: Optional[str] = Query(None, description="音量（如 '+0%', '-50%'）"),
    pitch: Optional[str] = Query(None, description="音调（如 '+0Hz', '-50Hz'）"),
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    将文本转换为语音音频
    
    支持的参数：
    - text: 要转换的文本（必需）
    - voice: 语音名称（可选，如 'en-US-JennyNeural'）
    - rate: 语速（可选，如 '+0%', '-50%'）
    - volume: 音量（可选，如 '+0%', '-50%'）
    - pitch: 音调（可选，如 '+0Hz', '-50Hz'）
    """
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="文本不能为空")
    
    try:
        # 如果是异步服务，直接使用异步方法
        from services.tts import EdgeTTSService, OpenAITTSService
        if isinstance(tts_service, (EdgeTTSService, OpenAITTSService)):
            if isinstance(tts_service, EdgeTTSService):
                audio_data = await tts_service._text_to_speech_async(
                    text=text.strip(),
                    voice=voice,
                    rate=rate,
                    volume=volume,
                    pitch=pitch
                )
            elif isinstance(tts_service, OpenAITTSService):
                audio_data = await tts_service._text_to_speech_async(
                    text=text.strip(),
                    voice=voice,
                    rate=rate,
                    volume=volume,
                    pitch=pitch
                )
        else:
            audio_data = tts_service.text_to_speech(
                text=text.strip(),
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch
            )
        
        if not audio_data:
            raise HTTPException(status_code=500, detail="音频生成失败")
        
        # 返回音频流
        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'attachment; filename="tts_audio.mp3"'
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS生成失败: {str(e)}")


@router.get("/voices")
async def list_voices(
    language: Optional[str] = Query(None, description="语言代码（如 'en', 'zh'），None 表示所有语言"),
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    列出可用的语音列表
    
    参数：
    - language: 语言代码（可选，如 'en', 'zh'），None 表示所有语言
    """
    try:
        # 如果是异步服务，直接使用异步方法
        from services.tts import EdgeTTSService, OpenAITTSService
        if isinstance(tts_service, EdgeTTSService):
            voices = await tts_service._list_voices_async(language=language)
        elif isinstance(tts_service, OpenAITTSService):
            # OpenAI TTS 的 list_voices 是同步的
            voices = tts_service.list_voices(language=language)
        else:
            voices = tts_service.list_voices(language=language)
        
        # 格式化返回数据
        result = []
        for voice in voices:
            result.append({
                "name": voice.get("ShortName", ""),
                "locale": voice.get("Locale", ""),
                "gender": voice.get("Gender", ""),
                "friendly_name": voice.get("FriendlyName", "")
            })
        
        return {
            "total": len(result),
            "voices": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取语音列表失败: {str(e)}")


@router.post("/text-to-speech-stream")
async def text_to_speech_stream(
    text: str = Query(..., description="要转换的文本"),
    voice: Optional[str] = Query(None, description="语音名称"),
    rate: Optional[str] = Query(None, description="语速"),
    volume: Optional[str] = Query(None, description="音量"),
    pitch: Optional[str] = Query(None, description="音调"),
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    将文本转换为语音音频（流式返回）
    
    适用于长文本，可以边生成边返回
    """
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="文本不能为空")
    
    try:
        import asyncio
        
        # 如果是 EdgeTTSService，使用异步方法
        if isinstance(tts_service, TTSServiceFactory.create("edge-tts")):
            from services.tts import EdgeTTSService
            if isinstance(tts_service, EdgeTTSService):
                async def generate_audio():
                    audio_data = await tts_service._text_to_speech_async(
                        text=text.strip(),
                        voice=voice,
                        rate=rate,
                        volume=volume,
                        pitch=pitch
                    )
                    return audio_data
                
                audio_data = await generate_audio()
            else:
                audio_data = tts_service.text_to_speech(
                    text=text.strip(),
                    voice=voice,
                    rate=rate,
                    volume=volume,
                    pitch=pitch
                )
        else:
            audio_data = tts_service.text_to_speech(
                text=text.strip(),
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch
            )
        
        if not audio_data:
            raise HTTPException(status_code=500, detail="音频生成失败")
        
        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/mpeg"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS生成失败: {str(e)}")

