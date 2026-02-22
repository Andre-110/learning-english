"""
会话缓存服务 - 支持断网重连和会话恢复

功能：
1. 断开连接时保存会话状态（对话历史、用户画像等）
2. 重连时恢复会话状态（5 分钟内有效）
3. 定期清理过期会话

参考：UserGenie OpenAI Voice Relay 的 SESSION_CACHE_TIMEOUT_MS 机制
"""
import time
import asyncio
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from threading import Lock

from services.utils.logger import get_logger

logger = get_logger("services.session_cache")


@dataclass
class CachedSession:
    """缓存的会话状态"""
    session_id: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    
    # 对话状态
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    user_profile: Dict[str, Any] = field(default_factory=dict)
    round_counter: int = 0
    
    # 时间戳
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    disconnected_at: float = 0
    
    # 状态标志
    is_disconnected: bool = False


class SessionCache:
    """
    会话缓存管理器
    
    使用方式：
        cache = SessionCache()
        
        # WebSocket 断开时
        cache.disconnect(session_id, session_context)
        
        # WebSocket 重连时
        restored = cache.try_restore(session_id)
        if restored:
            # 使用恢复的会话状态
            ...
    """
    
    # 默认超时：5 分钟
    DEFAULT_TIMEOUT_SECONDS = 5 * 60
    
    # 清理间隔：1 分钟
    CLEANUP_INTERVAL_SECONDS = 60
    
    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        self.timeout = timeout_seconds
        self.sessions: Dict[str, CachedSession] = {}
        self._lock = Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info(f"[SessionCache] 初始化, 超时时间: {timeout_seconds}s")
    
    def start_cleanup_task(self):
        """启动后台清理任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("[SessionCache] 后台清理任务已启动")
    
    async def _cleanup_loop(self):
        """定期清理过期会话"""
        while True:
            await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)
            self._cleanup_expired()
    
    def _cleanup_expired(self):
        """清理过期的会话"""
        now = time.time()
        expired = []
        
        with self._lock:
            for session_id, session in self.sessions.items():
                if session.is_disconnected:
                    elapsed = now - session.disconnected_at
                    if elapsed > self.timeout:
                        expired.append(session_id)
            
            for session_id in expired:
                del self.sessions[session_id]
                logger.info(f"[SessionCache] 清理过期会话: {session_id}")
        
        if expired:
            logger.info(f"[SessionCache] 已清理 {len(expired)} 个过期会话, 剩余: {len(self.sessions)}")
    
    def disconnect(
        self,
        session_id: str,
        session_context: Dict[str, Any]
    ) -> None:
        """
        标记会话为断开状态，保存上下文用于后续恢复
        
        Args:
            session_id: 会话 ID
            session_context: 当前会话上下文（包含 conversation_history 等）
        """
        with self._lock:
            # 提取需要保存的状态
            cached = CachedSession(
                session_id=session_id,
                user_id=session_context.get("user_id"),
                conversation_id=session_context.get("conversation_id"),
                conversation_history=session_context.get("conversation_history", []).copy(),
                user_profile=session_context.get("user_profile", {}).copy(),
                round_counter=session_context.get("round_counter", 0),
                created_at=session_context.get("created_at", time.time()),
                last_activity_at=session_context.get("last_activity_at", time.time()),
                disconnected_at=time.time(),
                is_disconnected=True,
            )
            
            self.sessions[session_id] = cached
            
            logger.info(
                f"[SessionCache] 会话已缓存: {session_id}, "
                f"对话历史: {len(cached.conversation_history)} 条, "
                f"轮次: {cached.round_counter}"
            )
    
    def try_restore(self, session_id: str) -> Optional[CachedSession]:
        """
        尝试恢复会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            恢复的会话状态，如果不存在或已过期返回 None
        """
        with self._lock:
            if session_id not in self.sessions:
                return None
            
            session = self.sessions[session_id]
            
            if not session.is_disconnected:
                # 会话仍在活动中（可能是重复连接）
                logger.warning(f"[SessionCache] 会话仍在活动中: {session_id}")
                return None
            
            # 检查是否过期
            elapsed = time.time() - session.disconnected_at
            if elapsed > self.timeout:
                logger.info(f"[SessionCache] 会话已过期: {session_id}, 断开时长: {elapsed:.1f}s")
                del self.sessions[session_id]
                return None
            
            # 恢复成功，标记为活动状态
            session.is_disconnected = False
            session.last_activity_at = time.time()
            
            logger.info(
                f"[SessionCache] 会话已恢复: {session_id}, "
                f"断开时长: {elapsed:.1f}s, "
                f"对话历史: {len(session.conversation_history)} 条"
            )
            
            return session
    
    def update_activity(self, session_id: str) -> None:
        """更新会话活动时间"""
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].last_activity_at = time.time()
    
    def remove(self, session_id: str) -> None:
        """移除会话（正常结束时调用）"""
        with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"[SessionCache] 会话已移除: {session_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            active = sum(1 for s in self.sessions.values() if not s.is_disconnected)
            disconnected = sum(1 for s in self.sessions.values() if s.is_disconnected)
            return {
                "total": len(self.sessions),
                "active": active,
                "disconnected": disconnected,
                "timeout_seconds": self.timeout,
            }


# 全局单例
_session_cache: Optional[SessionCache] = None


def get_session_cache() -> SessionCache:
    """获取全局会话缓存实例（自动启动清理任务）"""
    global _session_cache
    if _session_cache is None:
        _session_cache = SessionCache()
    # 确保清理任务已启动（需要在 asyncio 事件循环中调用）
    try:
        loop = asyncio.get_running_loop()
        if loop and (_session_cache._cleanup_task is None or _session_cache._cleanup_task.done()):
            _session_cache.start_cleanup_task()
    except RuntimeError:
        # 没有运行中的事件循环，跳过（清理任务会在首次异步调用时启动）
        pass
    return _session_cache
