"""
内存存储实现 - 用于开发和测试
"""
from typing import Optional, Dict, List
from models.conversation import Conversation
from models.user import UserProfile, CEFRLevel
from storage.repository import ConversationRepository, UserRepository


class MemoryConversationRepository(ConversationRepository):
    """内存对话存储实现"""
    
    def __init__(self):
        self._storage: Dict[str, Conversation] = {}
    
    def save(self, conversation: Conversation):
        """保存对话"""
        self._storage[conversation.conversation_id] = conversation
    
    def get(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话"""
        return self._storage.get(conversation_id)
    
    def get_by_user(self, user_id: str) -> List[Conversation]:
        """获取用户的所有对话"""
        return [conv for conv in self._storage.values() if conv.user_id == user_id]
    
    def delete(self, conversation_id: str):
        """删除对话"""
        if conversation_id in self._storage:
            del self._storage[conversation_id]


class MemoryUserRepository(UserRepository):
    """内存用户存储实现"""
    
    def __init__(self):
        self._storage: Dict[str, UserProfile] = {}
    
    def save(self, user_profile: UserProfile):
        """保存用户画像"""
        self._storage[user_profile.user_id] = user_profile
    
    def get(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        return self._storage.get(user_id)
    
    def get_or_create(self, user_id: str) -> UserProfile:
        """获取或创建用户画像"""
        if user_id in self._storage:
            return self._storage[user_id]
        else:
            profile = UserProfile(
                user_id=user_id,
                overall_score=0.0,
                cefr_level=CEFRLevel.A1
            )
            self._storage[user_id] = profile
            return profile
    
    def delete(self, user_id: str):
        """删除用户"""
        if user_id in self._storage:
            del self._storage[user_id]

