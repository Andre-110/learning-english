"""
Supabase 数据库存储实现
"""
from typing import Optional, Dict, List, Any
from datetime import datetime
from supabase import create_client, Client
from models.conversation import Conversation, Message, MessageRole, ConversationState
from models.user import UserProfile, CEFRLevel, InterestTag
from models.auth import UserAccount
from storage.repository import ConversationRepository, UserRepository, AuthRepository
from config.settings import Settings
from services.utils.logger import get_logger
import os
from dotenv import load_dotenv
import uuid

logger = get_logger("storage.supabase_repository")

load_dotenv()

# 获取配置
settings = Settings()

# Supabase 配置（优先使用环境变量，否则使用 settings，最后使用默认值）
SUPABASE_URL = os.getenv("SUPABASE_URL") or settings.supabase_url or "https://uxnqqkuviqlptltcepat.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or settings.supabase_key or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV4bnFxa3V2aXFscHRsdGNlcGF0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwODIzMDgsImV4cCI6MjA4MDY1ODMwOH0.oI7uVTWBXDnEhRgAsy_L4SZf2vGDpacwfKoEDS1DHsc"

# 模块级单例客户端（所有 Repository 共享）
_supabase_client: Optional[Client] = None

def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


class SupabaseConversationRepository(ConversationRepository):
    """Supabase 对话存储实现"""
    
    def __init__(self):
        self.client: Client = get_supabase_client()

    def save(self, conversation: Conversation):
        """保存对话"""
        # 提取讨论的主题和兴趣匹配信息（从消息metadata中提取）
        discussed_topics = []
        matched_interests = []
        interest_match_score = 0.0
        
        # 从第一条消息的metadata中提取（因为Conversation模型没有metadata字段）
        if conversation.messages:
            first_msg_metadata = conversation.messages[0].metadata or {}
            discussed_topics = first_msg_metadata.get("discussed_topics", [])
            matched_interests = first_msg_metadata.get("matched_interests", [])
            interest_match_score = first_msg_metadata.get("interest_match_score", 0.0)
        
        # 保存对话基本信息
        # 将discussed_topics等数据存储在metadata中，避免字段不存在的问题
        metadata = {}
        if discussed_topics:
            metadata["discussed_topics"] = discussed_topics
        if matched_interests:
            metadata["matched_interests"] = matched_interests
        if interest_match_score:
            metadata["interest_match_score"] = interest_match_score
        
        conv_data = {
            "conversation_id": conversation.conversation_id,
            "user_id": conversation.user_id,
            "state": conversation.state.value,
            "current_round": len(conversation.messages) // 2,  # 假设每轮包含 user 和 assistant 消息
            "summary": conversation.summary,
            "summary_round": conversation.summary_round,
            "started_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "ended_at": conversation.updated_at.isoformat() if conversation.state == ConversationState.COMPLETED else None,
        }
        
        # 将数据存储在metadata字段中（避免字段不存在的问题）
        if metadata:
            conv_data["metadata"] = metadata
        
        # 使用 upsert 插入或更新
        self.client.table("conversations").upsert(conv_data).execute()
        
        # 保存消息
        # 先删除旧消息（如果需要完全替换）
        try:
            self.client.table("messages").delete().eq("conversation_id", conversation.conversation_id).execute()
        except Exception as e:
            # 如果表不存在或删除失败，继续执行插入
            pass
        
        # 插入新消息
        if conversation.messages:
            messages_data = []
            current_round = 1
            for idx, message in enumerate(conversation.messages):
                # 根据消息角色判断轮次（每轮通常包含 user 和 assistant）
                if idx > 0 and message.role == MessageRole.USER:
                    current_round += 1
                
                msg_data = {
                    "conversation_id": conversation.conversation_id,
                    "round_number": current_round,
                    "sender_role": message.role.value,
                    "content": message.content,
                    "timestamp": message.timestamp.isoformat() if message.timestamp else None,
                    "metadata": message.metadata or {}
                }
                messages_data.append(msg_data)
            
            # 批量插入消息
            if messages_data:
                self.client.table("messages").insert(messages_data).execute()
    
    def get(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话"""
        # 获取对话基本信息
        conv_result = self.client.table("conversations").select("*").eq("conversation_id", conversation_id).execute()
        
        if not conv_result.data:
            return None
        
        conv_data = conv_result.data[0]
        
        # 获取消息
        messages_result = self.client.table("messages").select("*").eq("conversation_id", conversation_id).order("round_number").order("timestamp").execute()
        
        messages = []
        for msg_data in messages_result.data:
            try:
                # 处理时间戳
                timestamp_str = msg_data.get("timestamp")
                if timestamp_str:
                    # 处理 ISO 格式时间戳
                    if timestamp_str.endswith("Z"):
                        timestamp_str = timestamp_str[:-1] + "+00:00"
                    timestamp = datetime.fromisoformat(timestamp_str)
                else:
                    timestamp = datetime.now()
                
                message = Message(
                    role=MessageRole(msg_data["sender_role"]),
                    content=msg_data["content"],
                    timestamp=timestamp,
                    metadata=msg_data.get("metadata", {}) or {}
                )
                messages.append(message)
            except Exception as e:
                # 如果解析失败，使用默认值
                message = Message(
                    role=MessageRole(msg_data.get("sender_role", "user")),
                    content=msg_data.get("content", ""),
                    timestamp=datetime.now(),
                    metadata=msg_data.get("metadata", {}) or {}
                )
                messages.append(message)
        
        # 处理时间戳
        def parse_timestamp(ts_str):
            if not ts_str:
                return datetime.now()
            try:
                if ts_str.endswith("Z"):
                    ts_str = ts_str[:-1] + "+00:00"
                return datetime.fromisoformat(ts_str)
            except:
                return datetime.now()
        
        # 构建 Conversation 对象
        # 恢复元数据（从字段或metadata中获取）
        metadata = {}
        
        # 优先从metadata字段获取
        conv_metadata = conv_data.get("metadata", {}) or {}
        
        # 从独立字段或metadata中获取
        discussed_topics = conv_data.get("discussed_topics") or conv_metadata.get("discussed_topics", [])
        matched_interests = conv_data.get("matched_interests") or conv_metadata.get("matched_interests", [])
        interest_match_score = conv_data.get("interest_match_score")
        if interest_match_score is None:
            interest_match_score = conv_metadata.get("interest_match_score", 0.0)
        
        if discussed_topics:
            metadata["discussed_topics"] = discussed_topics
        if matched_interests:
            metadata["matched_interests"] = matched_interests
        if interest_match_score is not None:
            metadata["interest_match_score"] = interest_match_score
        
        # 处理状态值（兼容大小写）
        state_str = conv_data.get("state", "initializing").lower()
        try:
            state = ConversationState(state_str)
        except ValueError:
            # 如果状态值不匹配，尝试映射
            state_mapping = {
                "completed": ConversationState.COMPLETED,
                "in_progress": ConversationState.IN_PROGRESS,
                "initializing": ConversationState.INITIALIZING,
                "paused": ConversationState.PAUSED
            }
            state = state_mapping.get(state_str, ConversationState.INITIALIZING)
        
        conversation = Conversation(
            conversation_id=conv_data["conversation_id"],
            user_id=conv_data["user_id"],
            messages=messages,
            state=state,
            created_at=parse_timestamp(conv_data.get("started_at")),
            updated_at=parse_timestamp(conv_data.get("ended_at")),
            summary=conv_data.get("summary"),
            summary_round=conv_data.get("summary_round", 0)
        )
        
        # 设置元数据
        if metadata:
            # 需要更新Conversation模型以支持metadata字段，或者通过消息的metadata传递
            # 暂时通过第一条消息的metadata保存
            if conversation.messages:
                conversation.messages[0].metadata.update(metadata)
        
        return conversation
    
    def get_by_user(self, user_id: str) -> List[Conversation]:
        """获取用户的所有对话"""
        convs_result = self.client.table("conversations").select("conversation_id").eq("user_id", user_id).execute()
        
        conversations = []
        for conv_data in convs_result.data:
            conv = self.get(conv_data["conversation_id"])
            if conv:
                conversations.append(conv)
        
        return conversations
    
    def delete(self, conversation_id: str):
        """删除对话（外键级联删除会自动删除相关消息）"""
        self.client.table("conversations").delete().eq("conversation_id", conversation_id).execute()


class SupabaseUserRepository(UserRepository):
    """Supabase 用户存储实现"""

    def __init__(self):
        self.client: Client = get_supabase_client()
    
    def save(self, user_profile: UserProfile):
        """保存用户画像"""
        # 转换兴趣标签为字典格式
        interests_data = []
        for interest in user_profile.interests:
            interests_data.append({
                "category": interest.category,
                "tags": interest.tags,
                "weight": interest.weight,
                "last_discussed": interest.last_discussed
            })
        
        # 先获取现有用户的metadata（保留账户信息）
        existing_metadata = {}
        try:
            existing_user = self.client.table("users").select("metadata, username").eq("user_id", user_profile.user_id).execute()
            if existing_user.data:
                existing_metadata = existing_user.data[0].get("metadata", {}) or {}
                existing_username = existing_user.data[0].get("username")
        except:
            pass
        
        # 基础用户数据（不包含可能不存在的字段）
        user_data = {
            "user_id": user_profile.user_id,
            "username": existing_username if 'existing_username' in locals() and existing_username else user_profile.user_id,  # 保留现有username或使用user_id
            "overall_score": user_profile.overall_score,
            "cefr_level": user_profile.cefr_level.value,
            "strengths": user_profile.strengths,
            "weaknesses": user_profile.weaknesses,
            "conversation_count": user_profile.conversation_count,
            "last_login_at": datetime.now().isoformat()
        }
        
        # 将interests存储在metadata中（避免字段不存在的问题）
        # 注意：保留现有的metadata（如账户信息），只更新interests
        existing_metadata["interests"] = interests_data
        user_data["metadata"] = existing_metadata
        
        # 使用 upsert 插入或更新
        self.client.table("users").upsert(user_data).execute()
    
    def get(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        result = self.client.table("users").select("*").eq("user_id", user_id).execute()
        
        if not result.data:
            return None
        
        user_data = result.data[0]
        
        # 转换兴趣标签（从interests字段或metadata中获取）
        interests = []
        interests_data = user_data.get("interests", [])
        
        # 如果interests字段不存在，尝试从metadata中获取
        if not interests_data:
            metadata = user_data.get("metadata", {}) or {}
            interests_data = metadata.get("interests", [])
        
        if isinstance(interests_data, list):
            for item in interests_data:
                if isinstance(item, dict):
                    interests.append(InterestTag(
                        category=item.get("category", ""),
                        tags=item.get("tags", []),
                        weight=item.get("weight", 1.0),
                        last_discussed=item.get("last_discussed")
                    ))
        
        return UserProfile(
            user_id=user_data["user_id"],
            overall_score=user_data.get("overall_score", 0.0),
            cefr_level=CEFRLevel(user_data.get("cefr_level", "A1")),
            strengths=user_data.get("strengths", []),
            weaknesses=user_data.get("weaknesses", []),
            interests=interests,
            conversation_count=user_data.get("conversation_count", 0),
            last_updated=user_data.get("last_login_at")
        )
    
    def get_or_create(self, user_id: str) -> UserProfile:
        """获取或创建用户画像"""
        user_profile = self.get(user_id)
        
        if user_profile:
            return user_profile
        
        # 创建新用户
        user_profile = UserProfile(
            user_id=user_id,
            overall_score=0.0,
            cefr_level=CEFRLevel.A1
        )
        
        # 保存到数据库（save 方法会自动设置 username）
        self.save(user_profile)
        
        return user_profile
    
    def delete(self, user_id: str):
        """删除用户"""
        self.client.table("users").delete().eq("user_id", user_id).execute()
    
    def save_last_conversation_summary(self, user_id: str, summary: str, discussed_topics: List[str] = None) -> bool:
        """
        保存用户上次对话的摘要（跨对话持久化）
        
        存储在 users.metadata.last_conversation_summary 中
        
        Args:
            user_id: 用户 ID
            summary: 对话摘要（80字左右）
            discussed_topics: 讨论过的话题列表
            
        Returns:
            是否保存成功
        """
        try:
            # 获取现有 metadata
            result = self.client.table("users").select("metadata").eq("user_id", user_id).execute()
            
            if not result.data:
                logger.warning(f"[Summary] 用户不存在: {user_id}")
                return False
            
            metadata = result.data[0].get("metadata", {}) or {}
            
            # 更新摘要相关字段
            metadata["last_conversation_summary"] = summary
            metadata["last_conversation_time"] = datetime.now().isoformat()
            if discussed_topics:
                metadata["last_discussed_topics"] = discussed_topics[:10]  # 最多保留10个话题
            
            # 保存回数据库
            self.client.table("users").update({
                "metadata": metadata
            }).eq("user_id", user_id).execute()
            
            logger.info(f"[Summary] 已保存用户摘要: {user_id}, 长度={len(summary)}")
            return True
            
        except Exception as e:
            logger.error(f"[Summary] 保存摘要失败: {user_id}, error={e}")
            return False
    
    def get_last_conversation_summary(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户上次对话的摘要
        
        Args:
            user_id: 用户 ID
            
        Returns:
            {
                "summary": "对话摘要...",
                "time": "2024-01-15T10:30:00",
                "topics": ["topic1", "topic2"]
            }
            如果没有摘要则返回空字典
        """
        try:
            result = self.client.table("users").select("metadata").eq("user_id", user_id).execute()
            
            if not result.data:
                return {}
            
            metadata = result.data[0].get("metadata", {}) or {}
            
            summary = metadata.get("last_conversation_summary", "")
            if not summary:
                return {}
            
            return {
                "summary": summary,
                "time": metadata.get("last_conversation_time"),
                "topics": metadata.get("last_discussed_topics", [])
            }
            
        except Exception as e:
            logger.error(f"[Summary] 获取摘要失败: {user_id}, error={e}")
            return {}


class SupabaseAuthRepository(AuthRepository):
    """Supabase 认证存储实现"""

    def __init__(self):
        self.client: Client = get_supabase_client()
    
    def create_account(self, user_account: UserAccount) -> str:
        """创建用户账户"""
        account_data = {
            "user_id": user_account.user_id,
            "username": user_account.username,
            "email": user_account.email,
            "password_hash": user_account.password_hash,
            "is_active": user_account.is_active,
            "created_at": user_account.created_at.isoformat() if user_account.created_at else datetime.now().isoformat(),
            "updated_at": user_account.updated_at.isoformat() if user_account.updated_at else datetime.now().isoformat()
        }
        
        # 将账户信息存储在metadata中（避免字段不存在的问题）
        metadata = {"account": account_data}
        
        # 先检查users表是否存在，如果不存在则创建用户画像记录
        try:
            # 尝试获取用户（如果不存在则创建）
            existing = self.client.table("users").select("user_id").eq("user_id", user_account.user_id).execute()
            if not existing.data:
                # 创建基础用户记录
                self.client.table("users").insert({
                    "user_id": user_account.user_id,
                    "username": user_account.username,
                    "metadata": metadata
                }).execute()
            else:
                # 更新现有用户
                self.client.table("users").update({
                    "username": user_account.username,
                    "metadata": metadata
                }).eq("user_id", user_account.user_id).execute()
        except Exception as e:
            # 如果表结构不支持，将账户信息存储在metadata中
            self.client.table("users").upsert({
                "user_id": user_account.user_id,
                "username": user_account.username,
                "metadata": metadata
            }).execute()
        
        return user_account.user_id
    
    def get_account_by_username(self, username: str):
        """根据用户名获取账户"""
        result = self.client.table("users").select("*").eq("username", username).execute()
        
        if not result.data:
            return None
        
        user_data = result.data[0]
        return self._extract_account_from_user_data(user_data)
    
    def get_account_by_email(self, email: str):
        """根据邮箱获取账户"""
        # 由于email可能存储在metadata中，需要查询所有用户
        result = self.client.table("users").select("*").execute()
        
        for user_data in result.data:
            account = self._extract_account_from_user_data(user_data)
            if account and account.email == email:
                return account
        
        return None
    
    def get_account_by_user_id(self, user_id: str):
        """根据用户ID获取账户"""
        result = self.client.table("users").select("*").eq("user_id", user_id).execute()
        
        if not result.data:
            return None
        
        user_data = result.data[0]
        return self._extract_account_from_user_data(user_data)
    
    def _extract_account_from_user_data(self, user_data: dict):
        """从用户数据中提取账户信息"""
        # 尝试从metadata中获取账户信息
        metadata = user_data.get("metadata", {}) or {}
        account_data = metadata.get("account", {})
        
        if account_data:
            try:
                return UserAccount(
                    user_id=account_data.get("user_id") or user_data.get("user_id"),
                    username=account_data.get("username") or user_data.get("username"),
                    email=account_data.get("email"),
                    password_hash=account_data.get("password_hash", ""),
                    created_at=datetime.fromisoformat(account_data["created_at"]) if account_data.get("created_at") else None,
                    updated_at=datetime.fromisoformat(account_data["updated_at"]) if account_data.get("updated_at") else None,
                    is_active=account_data.get("is_active", True),
                    last_login=datetime.fromisoformat(account_data["last_login"]) if account_data.get("last_login") else None
                )
            except Exception as e:
                logger.warning(f"提取账户信息失败: {e}")
                return None
        
        # 如果没有账户信息，返回None（说明用户没有注册账户）
        return None
    
    def update_last_login(self, user_id: str):
        """更新最后登录时间"""
        try:
            user_data = self.client.table("users").select("metadata").eq("user_id", user_id).execute()
            if user_data.data:
                metadata = user_data.data[0].get("metadata", {}) or {}
                account_data = metadata.get("account", {})
                account_data["last_login"] = datetime.now().isoformat()
                metadata["account"] = account_data
                
                self.client.table("users").update({
                    "metadata": metadata
                }).eq("user_id", user_id).execute()
        except Exception as e:
            logger.warning(f"更新最后登录时间失败: {e}")
    
    def username_exists(self, username: str) -> bool:
        """检查用户名是否存在"""
        result = self.client.table("users").select("user_id").eq("username", username).execute()
        return len(result.data) > 0
    
    def email_exists(self, email: str) -> bool:
        """检查邮箱是否存在"""
        if not email:
            return False
        
        # 由于email可能存储在metadata中，需要查询所有用户
        result = self.client.table("users").select("*").execute()
        
        for user_data in result.data:
            metadata = user_data.get("metadata", {}) or {}
            account_data = metadata.get("account", {})
            if account_data.get("email") == email:
                return True
        
        return False

