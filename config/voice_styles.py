"""
语音风格配置

定义不同的 AI 语音风格，让用户可以选择自己喜欢的风格。

OpenAI gpt-4o-mini-tts 支持两种方式控制语音：
1. voice: 基础音色 (alloy, echo, fable, onyx, nova, shimmer)
2. instructions: 语音风格指令（控制情感、语调、语速等）

参考其他项目的实现：
- UserGenie.ai: 通过 voice ID 选择不同音色
- MiniMax: 丰富的中文语音角色（青涩青年、御姐、甜美女性等）
- ElevenLabs: voice_settings 控制 stability、similarity_boost
- Hume: 专注情感语音
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class VoiceStyle:
    """语音风格配置"""
    id: str
    name: str  # 显示名称
    name_zh: str  # 中文名称
    description: str  # 描述
    description_zh: str  # 中文描述
    voice: str  # OpenAI TTS 语音 (alloy, echo, fable, onyx, nova, shimmer)
    speed: float  # 语速 (0.25 - 4.0)
    instructions: str  # 语音风格指令


# 预定义的语音风格
VOICE_STYLES: Dict[str, VoiceStyle] = {
    # 🌟 友好热情型 - 默认推荐
    "friendly": VoiceStyle(
        id="friendly",
        name="Friendly Tutor",
        name_zh="友好导师",
        description="Warm and encouraging, like a patient friend",
        description_zh="温暖鼓励，像耐心的朋友",
        voice="nova",
        speed=0.95,
        instructions=(
            "Speak in a warm, friendly, and encouraging tone like a supportive friend. "
            "Use natural pauses between sentences. Vary your pitch and intonation to sound engaged. "
            "When the learner makes a mistake, sound understanding and supportive, not critical. "
            "Celebrate their successes with genuine enthusiasm. "
            "Avoid sounding robotic, monotone, or overly formal."
        )
    ),

    # 📚 专业教师型
    "professional": VoiceStyle(
        id="professional",
        name="Professional Teacher",
        name_zh="专业教师",
        description="Clear and articulate, like a language instructor",
        description_zh="清晰专业，像语言教师",
        voice="alloy",
        speed=0.9,
        instructions=(
            "Speak clearly and articulately like a professional language teacher. "
            "Enunciate each word precisely to help the learner understand pronunciation. "
            "Use a calm, measured pace with clear pauses between phrases. "
            "Sound knowledgeable and confident, but approachable. "
            "When correcting mistakes, be constructive and educational."
        )
    ),

    # ⚡ 活力充沛型
    "energetic": VoiceStyle(
        id="energetic",
        name="Energetic Coach",
        name_zh="活力教练",
        description="Upbeat and motivating, keeps you engaged",
        description_zh="活力四射，保持你的投入",
        voice="shimmer",
        speed=1.05,
        instructions=(
            "Speak with high energy and enthusiasm like an excited sports coach! "
            "Use dynamic intonation with lots of variation in pitch. "
            "Sound genuinely excited about the learner's progress. "
            "Use encouraging phrases naturally. "
            "Make learning feel fun and exciting, not like a chore."
        )
    ),

    # 🧘 沉稳平和型
    "calm": VoiceStyle(
        id="calm",
        name="Calm Guide",
        name_zh="沉稳向导",
        description="Soothing and relaxed, reduces anxiety",
        description_zh="舒缓放松，减少焦虑",
        voice="onyx",
        speed=0.85,
        instructions=(
            "Speak in a calm, soothing, and reassuring tone. "
            "Use a slower pace with gentle pauses to help the learner feel relaxed. "
            "Sound patient and understanding, never rushed or impatient. "
            "Create a safe, low-pressure environment for practice. "
            "When the learner struggles, respond with gentle encouragement."
        )
    ),

    # 📖 故事讲述型
    "storyteller": VoiceStyle(
        id="storyteller",
        name="Storyteller",
        name_zh="故事讲述者",
        description="Expressive and dramatic, like telling stories",
        description_zh="富有表现力，像讲故事",
        voice="fable",
        speed=0.95,
        instructions=(
            "Speak like an engaging storyteller with expressive, dramatic delivery. "
            "Use varied intonation to create interest and suspense. "
            "Add emotion and character to your voice - sound curious, surprised, thoughtful. "
            "Make the conversation feel like an adventure or a story unfolding. "
            "Use rhetorical questions and dramatic pauses to keep the learner engaged."
        )
    ),

    # 🎭 自然对话型
    "natural": VoiceStyle(
        id="natural",
        name="Natural Conversation",
        name_zh="自然对话",
        description="Most human-like, casual everyday style",
        description_zh="最像真人，日常闲聊风格",
        voice="echo",
        speed=1.0,
        instructions=(
            "Speak exactly like a native English speaker in casual conversation. "
            "Use natural speech patterns including slight hesitations occasionally. "
            "Vary your pace naturally - speed up when excited, slow down when thinking. "
            "React naturally to what the learner says with appropriate emotional responses. "
            "Sound like a real person having a genuine conversation, not an AI assistant."
        )
    ),
}

# 默认风格
DEFAULT_STYLE_ID = "friendly"


def get_voice_style(style_id: str) -> VoiceStyle:
    """
    获取语音风格配置

    Args:
        style_id: 风格 ID

    Returns:
        VoiceStyle 配置，如果不存在返回默认的 friendly 风格
    """
    return VOICE_STYLES.get(style_id, VOICE_STYLES[DEFAULT_STYLE_ID])


def get_all_voice_styles() -> Dict[str, VoiceStyle]:
    """获取所有语音风格"""
    return VOICE_STYLES


def get_voice_style_options() -> list:
    """
    获取语音风格选项列表（用于前端展示）

    Returns:
        [{"id": "friendly", "name": "Friendly Tutor", ...}, ...]
    """
    return [
        {
            "id": style.id,
            "name": style.name,
            "name_zh": style.name_zh,
            "description": style.description,
            "description_zh": style.description_zh,
            "voice": style.voice,
        }
        for style in VOICE_STYLES.values()
    ]
