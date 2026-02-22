"""
数据访问接口 - 定义存储抽象层
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from models.conversation import Conversation
from models.user import UserProfile


class ConversationRepository(ABC):
    """对话存储接口"""
    
    @abstractmethod
    def save(self, conversation: Conversation):
        """保存对话"""
        pass
    
    @abstractmethod
    def get(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话"""
        pass
    
    @abstractmethod
    def get_by_user(self, user_id: str) -> List[Conversation]:
        """获取用户的所有对话"""
        pass
    
    @abstractmethod
    def delete(self, conversation_id: str):
        """删除对话"""
        pass


class UserRepository(ABC):
    """用户存储接口"""
    
    @abstractmethod
    def save(self, user_profile: UserProfile):
        """保存用户画像"""
        pass
    
    @abstractmethod
    def get(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        pass
    
    @abstractmethod
    def get_or_create(self, user_id: str) -> UserProfile:
        """获取或创建用户画像"""
        pass
    
    @abstractmethod
    def delete(self, user_id: str):
        """删除用户"""
        pass


class AuthRepository(ABC):
    """用户认证存储接口"""
    
    @abstractmethod
    def create_account(self, user_account) -> str:
        """创建用户账户，返回user_id"""
        pass
    
    @abstractmethod
    def get_account_by_username(self, username: str):
        """根据用户名获取账户"""
        pass
    
    @abstractmethod
    def get_account_by_email(self, email: str):
        """根据邮箱获取账户"""
        pass
    
    @abstractmethod
    def get_account_by_user_id(self, user_id: str):
        """根据用户ID获取账户"""
        pass
    
    @abstractmethod
    def update_last_login(self, user_id: str):
        """更新最后登录时间"""
        pass
    
    @abstractmethod
    def username_exists(self, username: str) -> bool:
        """检查用户名是否存在"""
        pass
    
    @abstractmethod
    def email_exists(self, email: str) -> bool:
        """检查邮箱是否存在"""
        pass


class RepositoryFactory:
    """存储工厂 - 根据配置创建存储实例"""
    
    _default_backend: str = "supabase"  # 默认使用 Supabase
    
    @staticmethod
    def create_repositories(backend: str = None) -> tuple[ConversationRepository, UserRepository]:
        """创建存储实例"""
        backend = backend or RepositoryFactory._default_backend
        if backend == "memory":
            from storage.impl.memory_repository import (
                MemoryConversationRepository,
                MemoryUserRepository
            )
            return MemoryConversationRepository(), MemoryUserRepository()
        elif backend == "database" or backend == "supabase":
            from storage.impl.supabase_repository import (
                SupabaseConversationRepository,
                SupabaseUserRepository
            )
            return SupabaseConversationRepository(), SupabaseUserRepository()
        else:
            raise ValueError(f"Unsupported storage backend: {backend}")
    
    @staticmethod
    def create_user_repository(backend: str = None) -> UserRepository:
        """创建用户存储实例"""
        backend = backend or RepositoryFactory._default_backend
        if backend == "memory":
            from storage.impl.memory_repository import MemoryUserRepository
            return MemoryUserRepository()
        elif backend == "database" or backend == "supabase":
            from storage.impl.supabase_repository import SupabaseUserRepository
            return SupabaseUserRepository()
        else:
            raise ValueError(f"Unsupported storage backend: {backend}")
    
    @staticmethod
    def create_conversation_repository(backend: str = None) -> ConversationRepository:
        """创建对话存储实例"""
        backend = backend or RepositoryFactory._default_backend
        if backend == "memory":
            from storage.impl.memory_repository import MemoryConversationRepository
            return MemoryConversationRepository()
        elif backend == "database" or backend == "supabase":
            from storage.impl.supabase_repository import SupabaseConversationRepository
            return SupabaseConversationRepository()
        else:
            raise ValueError(f"Unsupported storage backend: {backend}")

