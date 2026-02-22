"""
系统常量定义

集中管理所有魔法数字和配置常量，避免硬编码散落在代码各处。
"""
import os

# ==========================================
# 音频处理常量
# ==========================================

# 音频缓冲区
AUDIO_CHUNK_SIZE = 4096  # 音频分块大小 (bytes)
MIN_AUDIO_SIZE = 10 * 1024  # 最小有效音频大小 (10KB)
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 最大音频大小 (10MB)

# 音频格式
DEFAULT_AUDIO_FORMAT = "wav"
SUPPORTED_AUDIO_FORMATS = ["wav", "mp3", "m4a", "webm", "ogg"]

# ==========================================
# 超时配置 (秒)
# ==========================================

# WebSocket 超时
WEBSOCKET_RECEIVE_TIMEOUT = 120  # 接收消息超时
WEBSOCKET_SEND_TIMEOUT = 30  # 发送消息超时

# ASR 超时
ASR_TIMEOUT = 30  # 语音识别超时

# ASR 首句保护（阶段 3 新增）
ASR_AUDIO_BUFFER_SIZE = int(os.getenv("ASR_AUDIO_BUFFER_SIZE", "300"))  # 音频缓冲帧数（约 10 秒）
ASR_PREWARM_CONNECTION = os.getenv("ASR_PREWARM_CONNECTION", "true").lower() == "true"  # 是否预热连接

# pVAD 噪音过滤（过滤背景音/他人声音，未注册声纹时退化为通用 VAD）
USE_PVAD = os.getenv("USE_PVAD", "false").lower() == "true"
PVAD_THRESHOLD = float(os.getenv("PVAD_THRESHOLD", "0.5"))

# LLM 超时
LLM_TIMEOUT = 60  # LLM 响应超时
LLM_STREAM_TIMEOUT = 120  # LLM 流式响应超时

# TTS 超时
TTS_TIMEOUT = 30  # TTS 合成超时

# 评估轨超时
EVALUATION_TIMEOUT = 60  # 评估超时
EVALUATION_STAGE_TIMEOUT = 25  # 单阶段评估超时 (原45s，降低以更快反馈)

# 评估节奏（每 N 轮输出一次评估）
EVALUATION_CADENCE_TURNS = int(os.getenv("EVALUATION_CADENCE_TURNS", "3"))
# 评估聚合（综合最近 N 轮用户输入）
EVALUATION_AGGREGATE_TURNS = int(os.getenv("EVALUATION_AGGREGATE_TURNS", "3"))

# 热点内容超时
HOT_CONTENT_GREETING_TIMEOUT = 8   # 开场白热点搜索超时（从5s增加到8s，Judy用户多次超时）
HOT_CONTENT_SEARCH_TIMEOUT = 20   # 被动触发热点搜索超时（不急，隔几轮再用）

# ==========================================
# 并发配置
# ==========================================

# 线程池
TTS_THREAD_POOL_SIZE = 2  # TTS 并行合成线程数
MAX_CONCURRENT_EVALUATIONS = 3  # 单用户最大并发评估数

# ==========================================
# 对话配置
# ==========================================

# 历史记录
MAX_CONVERSATION_HISTORY = 20  # 最大对话历史条数
INTERACTION_HISTORY_LIMIT = 6  # 交互轨历史限制 (3轮)
EVALUATION_HISTORY_LIMIT = 8  # 评估轨历史限制 (4轮)

# LLM 生成
LLM_MAX_TOKENS_RESPONSE = 150  # 回复最大 token
LLM_MAX_TOKENS_INITIAL = 100  # 初始问题最大 token
LLM_MAX_TOKENS_EVALUATION = 1000  # 评估最大 token
LLM_TEMPERATURE_RESPONSE = 0.7  # 回复温度
LLM_TEMPERATURE_INITIAL = 0.9  # 初始问题温度 (更多样化)
LLM_TEMPERATURE_EVALUATION = 0.3  # 评估温度 (更稳定)

# ==========================================
# TTS 配置
# ==========================================

TTS_DEFAULT_VOICE = "alloy"  # 默认语音
TTS_DEFAULT_SPEED = 1.0  # 默认语速
TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

# 分句策略
SENTENCE_FIRST_TRIGGER_LENGTH = 25  # 首句触发长度
SENTENCE_MIN_LENGTH = 8  # 最小句子长度
SENTENCE_COMMA_TRIGGER_LENGTH = 50  # 逗号分句触发长度
SENTENCE_FORCE_SPLIT_LENGTH = 80  # 强制分句长度

# ==========================================
# 缓存配置
# ==========================================

# 热点内容缓存
HOT_CONTENT_CACHE_TTL_HOURS = 1  # 热点内容缓存时间 (小时)
HOT_CONTENT_CACHE_MAX_SIZE = 50  # 最大缓存条目数

# ==========================================
# CEFR 评分标准
# ==========================================

CEFR_SCORE_RANGES = {
    "Pre-A1": (0, 15),
    "A1": (15, 30),
    "A2": (30, 45),
    "B1": (45, 60),
    "B2": (60, 75),
    "C1": (75, 90),
    "C2": (90, 101),  # 101 作为上限，确保 100 分包含在内
}

# 用户画像更新权重
PROFILE_HISTORY_WEIGHT = 0.7  # 历史分数权重
PROFILE_CURRENT_WEIGHT = 0.3  # 本轮分数权重

# ==========================================
# 通用热门话题 (热点轨使用)
# ==========================================

GENERAL_HOT_TOPICS = [
    "interesting science discoveries",
    "fun facts about the world",
    "trending technology news",
    "popular movies and TV shows",
    "amazing travel destinations",
    "health and wellness tips",
    "inspiring stories",
    "cultural events around the world",
]

# ==========================================
# API 模型配置
# ==========================================

# OpenAI 官方 API
OPENAI_ASR_MODEL = "gpt-4o-transcribe"
OPENAI_LLM_MODEL = "gpt-4o"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"

# Qwen-Omni
QWEN_OMNI_MODEL = "qwen3-omni-flash"

