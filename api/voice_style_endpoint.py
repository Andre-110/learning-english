"""
语音风格 API 端点

提供语音风格选项列表和设置接口

注意：语音预览使用前端静态音频文件（/audio/voice-preview-*.mp3）
生成脚本：scripts/generate_voice_previews.py
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from config.voice_styles import get_voice_style_options, get_voice_style, DEFAULT_STYLE_ID
from services.utils.logger import get_logger

logger = get_logger("api.voice_style")

router = APIRouter(prefix="/voice-style", tags=["Voice Style"])


class VoiceStyleOption(BaseModel):
    """语音风格选项"""
    id: str
    name: str
    name_zh: str
    description: str
    description_zh: str
    voice: str


class VoiceStyleListResponse(BaseModel):
    """语音风格列表响应"""
    styles: List[VoiceStyleOption]
    default_style_id: str


class SetVoiceStyleRequest(BaseModel):
    """设置语音风格请求"""
    style_id: str


class SetVoiceStyleResponse(BaseModel):
    """设置语音风格响应"""
    success: bool
    style_id: str
    style_name: str
    style_name_zh: str
    message: str


@router.get("/list", response_model=VoiceStyleListResponse)
async def list_voice_styles():
    """
    获取所有可用的语音风格选项

    Returns:
        语音风格列表和默认风格 ID
    """
    try:
        options = get_voice_style_options()
        return VoiceStyleListResponse(
            styles=options,
            default_style_id=DEFAULT_STYLE_ID
        )
    except Exception as e:
        logger.error(f"获取语音风格列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{style_id}", response_model=VoiceStyleOption)
async def get_voice_style_detail(style_id: str):
    """
    获取指定语音风格的详细信息

    Args:
        style_id: 风格 ID

    Returns:
        语音风格详情
    """
    style = get_voice_style(style_id)
    if not style:
        raise HTTPException(status_code=404, detail=f"Voice style '{style_id}' not found")

    return VoiceStyleOption(
        id=style.id,
        name=style.name,
        name_zh=style.name_zh,
        description=style.description,
        description_zh=style.description_zh,
        voice=style.voice
    )


@router.get("/{style_id}/preview")
async def preview_voice_style(style_id: str):
    """
    生成语音风格预览音频

    Args:
        style_id: 风格 ID

    Returns:
        PCM 音频数据 (16-bit, 24000Hz, mono)
    """
    style = get_voice_style(style_id)
    if not style:
        raise HTTPException(status_code=404, detail=f"Voice style '{style_id}' not found")

    # 获取预览文本
    preview_text = PREVIEW_TEXTS.get(style_id, DEFAULT_PREVIEW_TEXT)

    try:
        from services.gpt4o_pipeline import create_gpt4o_pipeline

        # 创建临时 pipeline 实例
        pipeline = create_gpt4o_pipeline()

        # 生成音频
        audio_data = pipeline.synthesize(
            text=preview_text,
            voice=style.voice,
            speed=style.speed,
            instructions=style.instructions,
            stream=False
        )

        logger.info(f"[Preview] 生成风格预览: {style_id}, 音频大小: {len(audio_data)} bytes")

        # 返回 PCM 音频（前端会播放）
        return Response(
            content=audio_data,
            media_type="audio/pcm",
            headers={
                "Content-Disposition": f"inline; filename=preview_{style_id}.pcm",
                "X-Audio-Sample-Rate": "24000",
                "X-Audio-Channels": "1",
                "X-Audio-Bits": "16"
            }
        )

    except Exception as e:
        logger.error(f"[Preview] 生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")

