"""
服务层 - 简化版

核心服务：
- llm: LLM 调用
- tts: 文字转语音
- speech: 语音转文字（标准流程）
- openrouter_audio: OpenRouter 一体化（推荐）
- unified_processor: 统一处理器（两套流程共用）
"""
from .llm import LLMService, LLMProvider

__all__ = [
    "LLMService",
    "LLMProvider",
]
