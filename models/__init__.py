"""
数据模型层 - 定义系统的核心数据结构
"""
from .user import UserProfile, CEFRLevel
from .conversation import Conversation, Message, ConversationState
from .assessment import AssessmentResult, DimensionScore, AbilityProfile

__all__ = [
    "UserProfile",
    "CEFRLevel",
    "Conversation",
    "Message",
    "ConversationState",
    "AssessmentResult",
    "DimensionScore",
    "AbilityProfile",
]






