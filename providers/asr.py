"""
ASR 适配器 - 语音识别服务

支持：
- OpenAI Whisper / GPT-4o-transcribe
- (未来) FunASR 本地模型
"""
from typing import Optional, Protocol

from openai import OpenAI

from config.settings import Settings
from config.constants import ASR_TIMEOUT, DEFAULT_AUDIO_FORMAT
from services.utils.logger import get_logger

logger = get_logger("providers.asr")
settings = Settings()


class ASRProvider(Protocol):
    """ASR 提供者协议 - 定义统一接口"""

    def transcribe(
        self,
        audio_data: bytes,
        audio_format: str = DEFAULT_AUDIO_FORMAT,
        language: str = "en",
        prompt: Optional[str] = None
    ) -> str:
        """
        语音转文字

        Args:
            audio_data: 音频二进制数据
            audio_format: 音频格式 (wav, mp3, m4a, webm)
            language: 语言代码 (en, zh)
            prompt: 提示词（用于提高识别准确率）

        Returns:
            转录文本
        """
        ...


class OpenAIASRProvider:
    """OpenAI ASR 实现 (Whisper / GPT-4o-transcribe)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化 OpenAI ASR

        Args:
            api_key: API 密钥，默认从 settings 读取
            base_url: API 基础 URL，默认从 settings 读取
            model: ASR 模型，默认从 settings 读取
        """
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_official_base_url
        self.model = model or settings.asr_model

        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY in .env")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=ASR_TIMEOUT
        )

        logger.info(f"[ASR] 初始化完成: model={self.model}")

    def transcribe(
        self,
        audio_data: bytes,
        audio_format: str = DEFAULT_AUDIO_FORMAT,
        language: str = "en",
        prompt: Optional[str] = None
    ) -> str:
        """语音转文字"""
        import time
        start_time = time.time()

        try:
            # 构建请求参数
            request_params = {
                "model": self.model,
                "file": (f"audio.{audio_format}", audio_data, f"audio/{audio_format}"),
                "language": language,
            }

            if prompt:
                request_params["prompt"] = prompt

            # 调用 API
            response = self.client.audio.transcriptions.create(**request_params)
            transcription = response.text.strip()

            elapsed = time.time() - start_time
            logger.info(f"[ASR] 完成, 耗时: {elapsed:.2f}s, 文本: {transcription[:50]}...")

            return transcription

        except Exception as e:
            logger.error(f"[ASR] 失败: {e}")
            raise


# 工厂函数
def create_asr_provider(provider_type: str = "openai", **kwargs) -> ASRProvider:
    """
    创建 ASR 提供者

    Args:
        provider_type: 提供者类型 ("openai", "funasr")
        **kwargs: 传递给提供者的参数

    Returns:
        ASR 提供者实例
    """
    if provider_type == "openai":
        return OpenAIASRProvider(**kwargs)
    # elif provider_type == "funasr":
    #     return FunASRProvider(**kwargs)
    else:
        raise ValueError(f"Unknown ASR provider: {provider_type}")

