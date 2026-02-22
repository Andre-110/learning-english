"""
LLM配置管理 - 集中管理所有LLM相关配置
"""
import os
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class LLMConfig:
    """LLM配置类 - 全局单例配置"""
    
    # OpenAI配置
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL")  # 代理地址，如 https://yunwu.ai
    PRIMARY_LLM_MODEL: str = os.getenv("PRIMARY_LLM_MODEL", "gpt-4-turbo")
    SECONDARY_LLM_MODEL: str = os.getenv("SECONDARY_LLM_MODEL", "gpt-3.5-turbo")
    
    # OpenRouter配置
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_AUDIO_MODEL: str = os.getenv("OPENROUTER_AUDIO_MODEL", "openai/gpt-4o-audio-preview")
    OPENROUTER_FAST_MODEL: str = os.getenv("OPENROUTER_FAST_MODEL", "openai/gpt-4o-mini")
    
    # Anthropic配置
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    
    # 豆包 ASR 配置
    DOUBAO_ASR_APP_KEY: Optional[str] = os.getenv("DOUBAO_ASR_APP_KEY")
    DOUBAO_ASR_ACCESS_KEY: Optional[str] = os.getenv("DOUBAO_ASR_ACCESS_KEY")
    
    # MiniMax TTS 配置
    MINIMAX_API_KEY: Optional[str] = os.getenv("MINIMAX_API_KEY")
    MINIMAX_TTS_MODEL: str = os.getenv("MINIMAX_TTS_MODEL", "speech-2.6-hd")
    MINIMAX_TTS_VOICE: str = os.getenv("MINIMAX_TTS_VOICE", "male-qn-jingying")
    
    # ASR 提供商: whisper, funasr, doubao
    ASR_PROVIDER: str = os.getenv("ASR_PROVIDER", "funasr").lower()
    
    # TTS 提供商: edge-tts, openai, minimax
    TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "openai").lower()
    
    # LLM提供商
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower()
    
    @classmethod
    def get_openai_base_url(cls) -> Optional[str]:
        """获取OpenAI base_url（自动处理/v1后缀）"""
        if not cls.OPENAI_BASE_URL:
            return None
        
        base_url = cls.OPENAI_BASE_URL.strip()
        # 确保以/v1结尾
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        
        return base_url
    
    @classmethod
    def get_openai_api_key(cls) -> Optional[str]:
        """获取OpenAI API密钥"""
        return cls.OPENAI_API_KEY
    
    @classmethod
    def get_anthropic_api_key(cls) -> Optional[str]:
        """获取Anthropic API密钥"""
        return cls.ANTHROPIC_API_KEY
    
    @classmethod
    def get_primary_model(cls) -> str:
        """获取主要模型"""
        return cls.PRIMARY_LLM_MODEL
    
    @classmethod
    def get_secondary_model(cls) -> str:
        """获取辅助模型"""
        return cls.SECONDARY_LLM_MODEL
    
    @classmethod
    def get_provider(cls) -> str:
        """获取LLM提供商"""
        return cls.LLM_PROVIDER
    
    @classmethod
    def get_openrouter_api_key(cls) -> Optional[str]:
        """获取OpenRouter API密钥"""
        return cls.OPENROUTER_API_KEY
    
    @classmethod
    def get_openrouter_base_url(cls) -> str:
        """获取OpenRouter base URL"""
        return cls.OPENROUTER_BASE_URL
    
    @classmethod
    def get_openrouter_audio_model(cls) -> str:
        """获取OpenRouter音频模型"""
        return cls.OPENROUTER_AUDIO_MODEL
    
    @classmethod
    def get_openrouter_fast_model(cls) -> str:
        """获取OpenRouter快速模型"""
        return cls.OPENROUTER_FAST_MODEL
    
    @classmethod
    def get_doubao_asr_config(cls) -> dict:
        """获取豆包 ASR 配置"""
        return {
            "app_key": cls.DOUBAO_ASR_APP_KEY or "",
            "access_key": cls.DOUBAO_ASR_ACCESS_KEY or ""
        }
    
    @classmethod
    def get_minimax_tts_config(cls) -> dict:
        """获取 MiniMax TTS 配置"""
        return {
            "api_key": cls.MINIMAX_API_KEY or "",
            "model": cls.MINIMAX_TTS_MODEL,
            "default_voice": cls.MINIMAX_TTS_VOICE
        }
    
    @classmethod
    def get_asr_provider(cls) -> str:
        """获取 ASR 提供商"""
        return cls.ASR_PROVIDER
    
    @classmethod
    def get_tts_provider(cls) -> str:
        """获取 TTS 提供商"""
        return cls.TTS_PROVIDER
    
    @classmethod
    def reload(cls):
        """重新加载配置（用于运行时更新）"""
        load_dotenv(override=True)
        cls.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        cls.OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
        cls.PRIMARY_LLM_MODEL = os.getenv("PRIMARY_LLM_MODEL", "gpt-4-turbo")
        cls.SECONDARY_LLM_MODEL = os.getenv("SECONDARY_LLM_MODEL", "gpt-3.5-turbo")
        cls.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        cls.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
        cls.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        cls.OPENROUTER_AUDIO_MODEL = os.getenv("OPENROUTER_AUDIO_MODEL", "openai/gpt-4o-audio-preview")
        cls.OPENROUTER_FAST_MODEL = os.getenv("OPENROUTER_FAST_MODEL", "openai/gpt-4o-mini")
        # 豆包和 MiniMax 配置
        cls.DOUBAO_ASR_APP_KEY = os.getenv("DOUBAO_ASR_APP_KEY")
        cls.DOUBAO_ASR_ACCESS_KEY = os.getenv("DOUBAO_ASR_ACCESS_KEY")
        cls.MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
        cls.MINIMAX_TTS_MODEL = os.getenv("MINIMAX_TTS_MODEL", "speech-2.6-hd")
        cls.MINIMAX_TTS_VOICE = os.getenv("MINIMAX_TTS_VOICE", "male-qn-jingying")
        cls.ASR_PROVIDER = os.getenv("ASR_PROVIDER", "funasr").lower()
        cls.TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai").lower()


# 全局配置实例
llm_config = LLMConfig()





