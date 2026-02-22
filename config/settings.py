"""
系统配置管理

所有配置从环境变量或 .env 文件读取，不要在代码中硬编码敏感信息。
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """系统配置 - 从环境变量读取"""
    
    # ==========================================
    # OpenAI 官方 API 配置 (用于三段链路)
    # ==========================================
    openai_api_key: Optional[str] = None  # 必须从环境变量设置
    anthropic_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None  # 自定义API地址（如代理服务）
    
    # 模型选择
    primary_llm_model: str = "gpt-4"
    secondary_llm_model: str = "gpt-3.5-turbo"
    llm_provider: str = "openai"  # openai, anthropic
    
    # 系统配置
    max_conversation_rounds: int = 20
    context_summary_interval: int = 5
    log_level: str = "INFO"
    
    # 存储配置
    storage_backend: str = "memory"  # memory, database, supabase
    
    # Supabase 配置
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    
    # 语音服务配置
    speech_provider: str = "whisper"  # whisper (API), funasr (local)
    funasr_model_dir: Optional[str] = None  # FunASR本地模型目录
    funasr_model_name: str = "iic/SenseVoiceSmall"  # FunASR模型名称
    funasr_language: str = "auto"  # FunASR语言设置（自动检测）
    
    # TTS服务配置
    tts_provider: str = "openai"  # edge-tts, openai
    tts_model: str = "gpt-4o-mini-tts"  # yunwu.ai 可能使用的模型名
    tts_default_voice: Optional[str] = "alloy"  # OpenAI TTS默认语音
    
    # OpenRouter 配置
    openrouter_api_key: Optional[str] = None
    openrouter_audio_model: str = "openai/gpt-4o-audio-preview"
    openrouter_fast_model: str = "openai/gpt-4o-mini"
    
    # 阿里云 DashScope 配置
    dashscope_api_key: Optional[str] = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_audio_model: str = "qwen-audio-turbo-latest"
    dashscope_fast_model: str = "qwen-flash"  # 便宜的文本模型，用于翻译和评估
    
    # LLM 服务选择 (openrouter, dashscope, qwen-omni)
    llm_service: str = "qwen-omni"
    
    # Qwen-Omni 配置
    qwen_omni_model: str = "qwen3-omni-flash"
    
    # ==========================================
    # OpenAI 官方 API 配置 (用于 GPT-4o Pipeline)
    # ==========================================
    # 注意：这些配置用于三段链路 (ASR → LLM → TTS)
    # 需要单独的官方 API Key（不同于代理服务的 key）
    openai_official_api_key: Optional[str] = None  # 从 .env 读取 OPENAI_OFFICIAL_API_KEY
    openai_official_base_url: str = "https://api.openai.com/v1"
    
    # 🆕 Deepgram 流式 ASR 配置
    deepgram_api_key: Optional[str] = None  # 从 .env 读取 DEEPGRAM_API_KEY
    deepgram_model: str = "nova-2"  # nova-2 是最新最快的模型
    use_streaming_asr: bool = False  # 是否启用流式 ASR（默认关闭，需配置 API Key）

    # 豆包 ASR 连接池（热备 / 连接复用）
    # 对应环境变量：USE_ASR_POOL=true/false
    use_asr_pool: bool = False
    
    # ASR 配置
    asr_provider: str = "openai"  # openai, doubao, deepgram
    asr_model: str = "gpt-4o-transcribe"
    asr_language: str = "en"
    
    # 豆包 ASR 配置
    doubao_asr_app_key: Optional[str] = None
    doubao_asr_access_key: Optional[str] = None
    doubao_asr_secret_key: Optional[str] = None
    doubao_asr_endpoint: Optional[str] = None
    
    # LLM 配置 (对话生成)
    pipeline_llm_model: str = "gpt-4o"
    pipeline_llm_temperature: float = 0.7
    pipeline_llm_max_tokens: int = 150
    
    # TTS 配置
    pipeline_tts_provider: str = "openai"  # openai, minimax, edge-tts
    pipeline_tts_model: str = "gpt-4o-mini-tts"
    pipeline_tts_voice: str = "nova"  # 默认语音
    pipeline_tts_speed: float = 1.0
    # 默认语音风格 (可选: friendly, professional, energetic, calm, storyteller)
    pipeline_tts_style: str = "friendly"
    
    # MiniMax TTS 配置
    minimax_api_key: Optional[str] = None
    minimax_tts_model: str = "speech-2.6-hd"
    minimax_tts_voice: str = "male-qn-jingying"  # 精英青年音色
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 单例实例
settings = Settings()

