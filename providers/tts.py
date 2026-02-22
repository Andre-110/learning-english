"""
TTS 适配器 - 语音合成服务

支持：
- OpenAI TTS (gpt-4o-mini-tts)
- (未来) Edge-TTS 等
"""
from typing import Optional, Generator, Protocol
import base64

from openai import OpenAI

from config.settings import Settings
from config.constants import TTS_TIMEOUT, AUDIO_CHUNK_SIZE
from services.utils.logger import get_logger

logger = get_logger("providers.tts")
settings = Settings()


class TTSProvider(Protocol):
    """TTS 提供者协议 - 定义统一接口"""

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        stream: bool = False
    ) -> Generator[bytes, None, None] | bytes:
        """
        文字转语音

        Args:
            text: 要合成的文本
            voice: 语音类型
            speed: 语速 (0.25 - 4.0)
            stream: 是否流式输出

        Returns:
            如果 stream=True，返回音频块生成器；否则返回完整音频
        """
        ...


class OpenAITTSProvider:
    """OpenAI TTS 实现 (gpt-4o-mini-tts)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        default_voice: Optional[str] = None,
        default_speed: Optional[float] = None
    ):
        """
        初始化 OpenAI TTS

        Args:
            api_key: API 密钥，默认从 settings 读取
            base_url: API 基础 URL，默认从 settings 读取
            model: TTS 模型，默认从 settings 读取
            default_voice: 默认语音
            default_speed: 默认语速
        """
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_official_base_url
        self.model = model or settings.pipeline_tts_model
        self.default_voice = default_voice or settings.pipeline_tts_voice
        self.default_speed = default_speed or settings.pipeline_tts_speed

        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY in .env")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=TTS_TIMEOUT
        )

        logger.info(f"[TTS] 初始化完成: model={self.model}, voice={self.default_voice}")

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        stream: bool = False
    ) -> Generator[bytes, None, None] | bytes:
        """文字转语音"""
        import time
        start_time = time.time()

        voice = voice or self.default_voice
        speed = speed or self.default_speed

        logger.info(f"[TTS] 请求: {len(text)} 字符, voice={voice}")

        try:
            if stream:
                return self._synthesize_stream(text, voice, speed, start_time)
            else:
                return self._synthesize_sync(text, voice, speed, start_time)
        except Exception as e:
            logger.error(f"[TTS] 失败: {e}")
            raise

    def _synthesize_sync(
        self,
        text: str,
        voice: str,
        speed: float,
        start_time: float
    ) -> bytes:
        """同步合成"""
        import time

        response = self.client.audio.speech.create(
            model=self.model,
            voice=voice,
            input=text,
            speed=speed,
            response_format="pcm"  # 返回原始 PCM 数据
        )

        audio_data = response.content

        elapsed = time.time() - start_time
        logger.info(f"[TTS] 完成, 耗时: {elapsed:.2f}s, 音频大小: {len(audio_data)} bytes")

        return audio_data

    def _synthesize_stream(
        self,
        text: str,
        voice: str,
        speed: float,
        start_time: float
    ) -> Generator[bytes, None, None]:
        """流式合成（分块返回）"""
        import time

        response = self.client.audio.speech.create(
            model=self.model,
            voice=voice,
            input=text,
            speed=speed,
            response_format="pcm"
        )

        # OpenAI TTS 返回完整响应，手动分块
        audio_data = response.content

        first_chunk = True
        for i in range(0, len(audio_data), AUDIO_CHUNK_SIZE):
            chunk = audio_data[i:i + AUDIO_CHUNK_SIZE]

            if first_chunk:
                ttfb = time.time() - start_time
                logger.info(f"[TTS] 首字节延迟 (TTFB): {ttfb:.2f}s")
                first_chunk = False

            yield chunk

        elapsed = time.time() - start_time
        logger.info(f"[TTS] 流式完成, 总耗时: {elapsed:.2f}s")

    def synthesize_to_base64(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None
    ) -> str:
        """合成并返回 base64 编码"""
        audio_data = self.synthesize(text, voice, speed, stream=False)
        return base64.b64encode(audio_data).decode("utf-8")


# 工厂函数
def create_tts_provider(provider_type: str = "openai", **kwargs) -> TTSProvider:
    """
    创建 TTS 提供者

    Args:
        provider_type: 提供者类型 ("openai", "edge-tts")
        **kwargs: 传递给提供者的参数

    Returns:
        TTS 提供者实例
    """
    if provider_type == "openai":
        return OpenAITTSProvider(**kwargs)
    # elif provider_type == "edge-tts":
    #     return EdgeTTSProvider(**kwargs)
    else:
        raise ValueError(f"Unknown TTS provider: {provider_type}")

