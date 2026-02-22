"""
外部服务适配器层 (Providers)

提供对外部 AI 服务的统一抽象，便于：
1. 测试时 mock
2. 未来切换供应商
3. 统一错误处理和重试逻辑

包含：
- ASR: 语音识别 (OpenAI Whisper, FunASR)
- LLM: 大语言模型 (GPT-4o, Qwen-Omni)
- TTS: 语音合成 (OpenAI TTS)
- Search: 网络搜索 (OpenAI web_search)
"""

from .asr import ASRProvider, create_asr_provider
from .llm import LLMProvider, create_llm_provider
from .tts import TTSProvider, create_tts_provider
from .search import SearchProvider, create_search_provider

__all__ = [
    "ASRProvider",
    "create_asr_provider",
    "LLMProvider",
    "create_llm_provider",
    "TTSProvider",
    "create_tts_provider",
    "SearchProvider",
    "create_search_provider",
]

