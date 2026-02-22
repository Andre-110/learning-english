"""
用户画像内存缓存 - 减少 Supabase 跨境延时

设计目标：
1. 首次查询后缓存用户画像，避免重复跨境查询
2. 新用户标记，跳过无效的数据库查询
3. TTL 过期机制，保证数据一致性

延时优化效果：
- 老用户首轮: 2000ms → 0ms (命中缓存)
- 新用户首轮: 2000ms → 0ms (跳过查询)
"""
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import threading

from services.utils.logger import get_logger

logger = get_logger("services.user_cache")


@dataclass
class CachedUserProfile:
    """缓存的用户画像"""
    profile: Optional[Dict[str, Any]]  # None 表示新用户
    cached_at: datetime
    is_new_user: bool = False  # 标记是否为新用户（数据库中不存在）
    
    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        """检查是否过期（默认 1 小时）"""
        return datetime.now() - self.cached_at > timedelta(seconds=ttl_seconds)


class UserProfileCache:
    """
    用户画像缓存
    
    功能：
    1. 缓存已查询的用户画像，避免重复查询
    2. 记录新用户，直接跳过数据库查询
    3. 支持手动失效（用户画像更新后）
    
    使用方式：
        cache = get_user_cache()
        
        # 查询（先查缓存）
        cached = cache.get(user_id)
        if cached is not None:
            if cached.is_new_user:
                # 新用户，使用默认值
                user_profile = {"cefr_level": "B1", "interests": []}
            else:
                # 老用户，使用缓存
                user_profile = cached.profile
        else:
            # 缓存未命中，查数据库
            db_profile = user_repo.get(user_id)
            cache.set(user_id, db_profile)
            ...
    """
    
    # 配置
    DEFAULT_TTL_SECONDS = 3600  # 默认 1 小时过期
    MAX_CACHE_SIZE = 1000  # 最大缓存条目
    CLEANUP_THRESHOLD = 1200  # 触发清理的阈值
    
    def __init__(self):
        self._cache: Dict[str, CachedUserProfile] = {}
        self._known_new_users: Set[str] = set()  # 已知的新用户（跳过查询）
        self._lock = threading.Lock()
        
        logger.info("[UserCache] 初始化完成")
    
    def get(self, user_id: str) -> Optional[CachedUserProfile]:
        """
        获取缓存的用户画像
        
        Returns:
            CachedUserProfile: 缓存命中
            None: 缓存未命中，需要查数据库
        """
        if not user_id:
            return None
            
        with self._lock:
            # 检查是否为已知新用户
            if user_id in self._known_new_users:
                logger.debug(f"[UserCache] 命中已知新用户: {user_id}")
                return CachedUserProfile(
                    profile=None,
                    cached_at=datetime.now(),
                    is_new_user=True
                )
            
            # 检查缓存
            cached = self._cache.get(user_id)
            if cached and not cached.is_expired(self.DEFAULT_TTL_SECONDS):
                logger.debug(f"[UserCache] 命中缓存: {user_id}, is_new={cached.is_new_user}")
                return cached
            
            # 缓存过期或不存在
            if cached:
                del self._cache[user_id]
                
            return None
    
    def set(self, user_id: str, profile: Optional[Dict[str, Any]], is_new_user: bool = False):
        """
        设置用户画像缓存
        
        Args:
            user_id: 用户 ID
            profile: 用户画像（None 表示新用户）
            is_new_user: 是否为新用户
        """
        if not user_id:
            return
            
        with self._lock:
            # 清理过大的缓存
            if len(self._cache) >= self.CLEANUP_THRESHOLD:
                self._cleanup()
            
            self._cache[user_id] = CachedUserProfile(
                profile=profile,
                cached_at=datetime.now(),
                is_new_user=is_new_user
            )
            
            # 记录新用户
            if is_new_user:
                self._known_new_users.add(user_id)
                
            logger.debug(f"[UserCache] 缓存用户: {user_id}, is_new={is_new_user}")
    
    def invalidate(self, user_id: str):
        """
        使用户缓存失效（用户画像更新后调用）
        """
        if not user_id:
            return
            
        with self._lock:
            if user_id in self._cache:
                del self._cache[user_id]
            if user_id in self._known_new_users:
                self._known_new_users.remove(user_id)
                
            logger.debug(f"[UserCache] 失效缓存: {user_id}")
    
    def mark_as_registered(self, user_id: str):
        """
        标记用户已注册（新用户首次保存画像后调用）
        """
        if not user_id:
            return
            
        with self._lock:
            if user_id in self._known_new_users:
                self._known_new_users.remove(user_id)
                
            logger.debug(f"[UserCache] 标记为已注册: {user_id}")
    
    def _cleanup(self):
        """清理过期缓存"""
        now = datetime.now()
        expired_keys = [
            k for k, v in self._cache.items()
            if v.is_expired(self.DEFAULT_TTL_SECONDS)
        ]
        
        for key in expired_keys:
            del self._cache[key]
            
        # 如果还是太大，删除最旧的
        if len(self._cache) > self.MAX_CACHE_SIZE:
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: x[1].cached_at
            )
            for key, _ in sorted_items[:len(self._cache) - self.MAX_CACHE_SIZE]:
                del self._cache[key]
                
        logger.info(f"[UserCache] 清理完成, 剩余: {len(self._cache)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            return {
                "cached_users": len(self._cache),
                "known_new_users": len(self._known_new_users),
                "max_size": self.MAX_CACHE_SIZE,
                "ttl_seconds": self.DEFAULT_TTL_SECONDS,
            }


# 全局单例
_user_cache: Optional[UserProfileCache] = None


def get_user_cache() -> UserProfileCache:
    """获取用户缓存单例"""
    global _user_cache
    if _user_cache is None:
        _user_cache = UserProfileCache()
    return _user_cache


# ==========================================
# 新用户引导开场白
# ==========================================

NEW_USER_GREETING_TEMPLATES = [
    # 友好引导型
    "Hey there! 👋 I'm excited to chat with you! Before we dive in, I'm curious - what topics do you love talking about? Movies, music, sports, tech, travel... What gets you excited?",
    
    # 轻松对话型
    "Hi! Great to meet you! 🎉 I'd love to know a bit about you - what are some things you're really into these days? Could be anything - hobbies, shows you're watching, games you play...",
    
    # 问题驱动型
    "Hello! 😊 So glad you're here! Quick question to help us have better chats: What topics make you light up? Maybe sports, music, food, or something totally unique?",
]

def get_new_user_greeting() -> str:
    """获取新用户引导开场白"""
    import random
    return random.choice(NEW_USER_GREETING_TEMPLATES)


# ==========================================
# 默认用户画像（新用户）
# ==========================================

def get_default_user_profile() -> Dict[str, Any]:
    """获取新用户的默认画像"""
    return {
        "cefr_level": "B1",  # 中等难度
        "interests": [],     # 空兴趣（等待提取）
        "is_new_user": True, # 标记为新用户
    }
