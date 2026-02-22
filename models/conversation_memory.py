"""
对话记忆管理模块

三层记忆架构：
- Layer 1: 持久记忆 (Persistent Memory) - 存储在 user_profile
- Layer 2: 会话摘要 (Session Summary) - 本次会话的压缩摘要
- Layer 3: 短期记忆 (Short-term Memory) - 最近的完整对话

参考实现：
- Anthropic Quickstarts: Token-Aware 截断
- UserGenie.ai: Multi-Prompt Agent 状态机
- Stimm: RAG + 对话历史
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def count_tokens(text: str) -> int:
    """
    计算文本的 token 数量
    
    优先使用 tiktoken（精确），降级使用简单估算
    """
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model("gpt-4o")
        return len(encoding.encode(text))
    except ImportError:
        # tiktoken 未安装，使用简单估算
        # 英文约 4 字符/token，中文约 1.5 字符/token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + english_chars / 4)
    except Exception as e:
        logger.warning(f"Token counting failed: {e}, using fallback")
        return len(text) // 3


@dataclass
class Message:
    """单条消息"""
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    token_count: int = 0
    
    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = count_tokens(self.content)


@dataclass
class ConversationMemory:
    """
    对话记忆管理器
    
    实现三层记忆架构，支持：
    - Token-Aware 动态截断
    - 会话摘要生成
    - 持久记忆更新
    """
    
    # === 配置 (🆕 2026-01-26: 降低上限减少延迟) ===
    max_short_term_tokens: int = 1200      # 短期记忆 Token 上限 (原2000，降低以减少LLM延迟)
    max_short_term_turns: int = 6          # 短期记忆轮数上限 (原8)
    summary_trigger_turns: int = 3         # 触发摘要的轮数阈值 (原5，更早生成摘要)
    max_message_display_length: int = 500  # 单条消息显示长度上限
    
    # === Layer 1: 持久记忆（从 user_profile 加载）===
    user_profile: Dict[str, Any] = field(default_factory=dict)
    
    # === Layer 2: 会话摘要 ===
    session_summary: str = ""
    is_cross_session_summary: bool = False  # 🆕 标记是否为跨对话摘要
    discussed_topics: List[str] = field(default_factory=list)
    key_facts_this_session: List[str] = field(default_factory=list)
    summary_pending: bool = False  # 标记是否需要生成摘要
    
    # === Layer 3: 短期记忆 ===
    messages: List[Message] = field(default_factory=list)
    total_tokens: int = 0
    turn_count: int = 0
    
    # === 元数据 ===
    truncation_notice_sent: bool = False
    messages_before_truncation: int = 0  # 截断前的消息数（用于判断是否截断过）
    
    def add_message(self, role: str, content: str) -> None:
        """
        添加消息到短期记忆
        
        自动处理：
        1. Token 计数
        2. 超限截断
        3. 摘要触发标记
        """
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.total_tokens += msg.token_count
        self.messages_before_truncation = len(self.messages)
        
        if role == "user":
            self.turn_count += 1
        
        logger.debug(
            f"[Memory] Added {role} message: {msg.token_count} tokens, "
            f"total: {self.total_tokens}/{self.max_short_term_tokens}"
        )
        
        # 检查是否需要压缩
        self._maybe_compress()
    
    def _maybe_compress(self) -> None:
        """检查并执行压缩策略"""
        # 策略 1: Token 超限 → 截断
        if self.total_tokens > self.max_short_term_tokens:
            self._truncate_by_tokens()
        
        # 策略 2: 轮数超限 → 截断（备用）
        if len(self.messages) > self.max_short_term_turns * 2:
            self._truncate_by_turns()
        
        # 策略 3: 轮数达到阈值 → 标记需要生成摘要
        if self.turn_count > 0 and self.turn_count % self.summary_trigger_turns == 0:
            self.summary_pending = True
            logger.info(f"[Memory] Summary generation pending (turn {self.turn_count})")
    
    def _truncate_by_tokens(self) -> None:
        """
        基于 Token 数量截断（参考 Anthropic 实现）
        
        策略：移除最早的消息对（user + assistant），直到 Token 数在限制内
        """
        truncated_count = 0
        
        while self.total_tokens > self.max_short_term_tokens and len(self.messages) > 2:
            # 移除最早的消息
            removed = self.messages.pop(0)
            self.total_tokens -= removed.token_count
            truncated_count += 1
            
            # 如果移除的是 user，尝试也移除对应的 assistant 回复
            if removed.role == "user" and self.messages and self.messages[0].role == "assistant":
                removed_assistant = self.messages.pop(0)
                self.total_tokens -= removed_assistant.token_count
                truncated_count += 1
        
        if truncated_count > 0:
            self.truncation_notice_sent = True
            logger.info(
                f"[Memory] Truncated {truncated_count} messages by token limit, "
                f"remaining: {len(self.messages)} messages, {self.total_tokens} tokens"
            )
    
    def _truncate_by_turns(self) -> None:
        """基于轮数截断（备用策略）"""
        target_messages = self.max_short_term_turns * 2
        
        while len(self.messages) > target_messages:
            removed = self.messages.pop(0)
            self.total_tokens -= removed.token_count
        
        self.truncation_notice_sent = True
        logger.info(f"[Memory] Truncated by turn limit, remaining: {len(self.messages)} messages")
    
    def get_context_for_llm(self) -> str:
        """
        构建发送给 LLM 的完整上下文
        
        结构：
        1. 持久记忆（用户画像）
        2. 会话摘要（如果有）
        3. 截断提示（如果有）
        4. 短期记忆（最近对话）
        
        Returns:
            格式化的上下文字符串
        """
        sections = []
        
        # === Layer 1: 持久记忆 ===
        profile_section = self._build_profile_section()
        if profile_section:
            sections.append(profile_section)
        
        # === Layer 2: 会话摘要 ===
        summary_section = self._build_summary_section()
        if summary_section:
            sections.append(summary_section)
        
        # === 截断提示 ===
        if self.truncation_notice_sent:
            sections.append("[Earlier messages have been summarized to save space]\n")
        
        # === Layer 3: 短期记忆 ===
        recent_section = self._build_recent_section()
        if recent_section:
            sections.append(recent_section)
        
        return "\n".join(sections)
    
    def _build_profile_section(self) -> str:
        """构建用户画像部分"""
        if not self.user_profile:
            return ""
        
        lines = ["## User Profile (Long-term Memory)"]
        
        # 兴趣 (区分最新焦点和长期兴趣)
        interests = self.user_profile.get("interests", [])
        if interests:
            if isinstance(interests, list):
                # 假设列表末尾是最新的
                latest = interests[-3:]
                general = interests[:-3]
                
                if latest:
                    lines.append(f"- ⚡️ CURRENT FOCUS: {', '.join(str(i) for i in latest)}")
                if general:
                    # 随机取几个长期兴趣，避免 Prompt 过长
                    import random
                    sample = random.sample(general, min(len(general), 5))
                    lines.append(f"- Other Interests: {', '.join(str(i) for i in sample)}")
            else:
                lines.append(f"- Interests: {str(interests)}")
        
        # CEFR 等级
        cefr = self.user_profile.get("cefr_level")
        if cefr:
            lines.append(f"- English Level: {cefr}")
        
        # 优点
        strengths = self.user_profile.get("strengths", [])
        if strengths and isinstance(strengths, list):
            strengths_str = ", ".join(str(s) for s in strengths[:3])
            lines.append(f"- Strengths: {strengths_str}")
        
        # 弱点
        weaknesses = self.user_profile.get("weaknesses", [])
        if weaknesses and isinstance(weaknesses, list):
            weaknesses_str = ", ".join(str(w) for w in weaknesses[:3])
            lines.append(f"- Areas to improve: {weaknesses_str}")
        
        if len(lines) > 1:  # 有内容
            return "\n".join(lines) + "\n"
        return ""
    
    def _build_summary_section(self) -> str:
        """构建会话摘要部分"""
        sections = []
        
        if self.session_summary:
            # 🆕 根据是否跨对话使用不同的标题
            if self.is_cross_session_summary:
                sections.append(f"## From Previous Conversation\n{self.session_summary}")
            else:
                sections.append(f"## Earlier in This Conversation\n{self.session_summary}")
        
        if self.discussed_topics:
            topics_str = ", ".join(self.discussed_topics[:5])
            sections.append(f"Topics discussed so far: {topics_str}")
        
        if sections:
            return "\n".join(sections) + "\n"
        return ""
    
    def _build_recent_section(self) -> str:
        """构建最近对话部分"""
        if not self.messages:
            return ""
        
        lines = ["## Recent Conversation"]
        
        for msg in self.messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            # 限制单条消息长度
            content = msg.content
            if len(content) > self.max_message_display_length:
                content = content[:self.max_message_display_length] + "..."
            lines.append(f"{role_label}: {content}")
        
        return "\n".join(lines)
    
    def get_messages_for_api(self) -> List[Dict[str, str]]:
        """
        获取发送给 API 的消息列表格式
        
        Returns:
            [{"role": "user", "content": "..."}, ...]
        """
        return [{"role": msg.role, "content": msg.content} for msg in self.messages]
    
    def get_recent_messages(self, n: int = 6) -> List[Dict[str, str]]:
        """
        获取最近 N 条消息
        
        Args:
            n: 消息数量
            
        Returns:
            消息列表
        """
        recent = self.messages[-n:] if len(self.messages) > n else self.messages
        return [{"role": msg.role, "content": msg.content} for msg in recent]
    
    def extract_and_update_profile(
        self,
        evaluation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从评估结果中提取信息并更新用户画像
        
        Args:
            evaluation_result: 评估轨返回的结果
            
        Returns:
            需要持久化到数据库的更新字典
        """
        updates = {}
        
        # 提取兴趣点
        new_interests = evaluation_result.get("interests", [])
        if new_interests and isinstance(new_interests, list):
            existing = self.user_profile.get("interests", [])
            if not isinstance(existing, list):
                existing = []
            
            # 合并去重，新的在后（列表末尾 = 最新）
            merged = []
            seen = set()
            
            # 先添加旧的
            for interest in existing:
                if isinstance(interest, str) and interest.lower() not in seen:
                    merged.append(interest)
                    seen.add(interest.lower())
            
            # 再追加新的
            for interest in new_interests:
                if isinstance(interest, str) and interest.lower() not in seen:
                    merged.append(interest)
                    seen.add(interest.lower())
            
            # 保持列表长度（保留最新的 20 个，而不是截断旧的）
            merged = merged[-20:]
            
            if merged != existing:
                updates["interests"] = merged
                self.user_profile["interests"] = merged
        
        # 更新讨论过的话题（会话级，不持久化）
        if new_interests:
            for topic in new_interests:
                if isinstance(topic, str) and topic not in self.discussed_topics:
                    self.discussed_topics.append(topic)
        
        # 提取优缺点（如果评估结果包含）
        if "strengths" in evaluation_result:
            new_strengths = evaluation_result["strengths"]
            if isinstance(new_strengths, list) and new_strengths:
                existing = self.user_profile.get("strengths", [])
                if not isinstance(existing, list):
                    existing = []
                merged = list(dict.fromkeys(new_strengths + existing))[:5]
                if merged != existing:
                    updates["strengths"] = merged
                    self.user_profile["strengths"] = merged
        
        if "weaknesses" in evaluation_result:
            new_weaknesses = evaluation_result["weaknesses"]
            if isinstance(new_weaknesses, list) and new_weaknesses:
                existing = self.user_profile.get("weaknesses", [])
                if not isinstance(existing, list):
                    existing = []
                merged = list(dict.fromkeys(new_weaknesses + existing))[:5]
                if merged != existing:
                    updates["weaknesses"] = merged
                    self.user_profile["weaknesses"] = merged
        
        if updates:
            logger.info(f"[Memory] Profile updates: {list(updates.keys())}")
        
        return updates
    
    def set_session_summary(self, summary: str, is_cross_session: bool = False) -> None:
        """
        设置会话摘要
        
        Args:
            summary: 摘要文本
            is_cross_session: 是否为跨对话摘要（加载上次对话的摘要）
        """
        self.session_summary = summary
        self.is_cross_session_summary = is_cross_session
        self.summary_pending = False
        logger.info(f"[Memory] Session summary updated (cross_session={is_cross_session}): {summary[:50]}...")
    
    def get_messages_for_summary(self) -> List[Dict[str, str]]:
        """
        获取需要生成摘要的消息
        
        返回被截断的早期消息（如果有）或所有消息的前半部分
        """
        if self.truncation_notice_sent:
            # 已截断，返回当前所有消息用于生成摘要
            return self.get_messages_for_api()
        
        # 未截断，返回前半部分消息
        half = len(self.messages) // 2
        if half < 2:
            return []
        
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.messages[:half]
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        return {
            "total_messages": len(self.messages),
            "total_tokens": self.total_tokens,
            "turn_count": self.turn_count,
            "truncated": self.truncation_notice_sent,
            "has_summary": bool(self.session_summary),
            "discussed_topics": self.discussed_topics,
            "profile_interests": self.user_profile.get("interests", []),
        }
    
    def clear(self) -> None:
        """清空短期记忆（保留持久记忆）"""
        self.messages.clear()
        self.total_tokens = 0
        self.turn_count = 0
        self.truncation_notice_sent = False
        self.session_summary = ""
        self.discussed_topics.clear()
        self.key_facts_this_session.clear()
        self.summary_pending = False
        logger.info("[Memory] Short-term memory cleared")


# === 全局记忆管理 ===

_user_memories: Dict[str, ConversationMemory] = {}


def get_or_create_memory(
    user_id: str,
    user_profile: Optional[Dict[str, Any]] = None
) -> ConversationMemory:
    """
    获取或创建用户的对话记忆
    
    Args:
        user_id: 用户 ID
        user_profile: 用户画像（首次创建时使用）
        
    Returns:
        ConversationMemory 实例
    """
    if user_id not in _user_memories:
        _user_memories[user_id] = ConversationMemory(
            user_profile=user_profile or {},
            max_short_term_tokens=1200,
            summary_trigger_turns=5
        )
        logger.info(f"[Memory] Created new memory for user: {user_id}")
    elif user_profile:
        # 更新已有记忆的用户画像
        _user_memories[user_id].user_profile.update(user_profile)
    
    return _user_memories[user_id]


def clear_user_memory(user_id: str) -> None:
    """清除用户的对话记忆"""
    if user_id in _user_memories:
        _user_memories[user_id].clear()
        logger.info(f"[Memory] Cleared memory for user: {user_id}")


def remove_user_memory(user_id: str) -> None:
    """完全移除用户的记忆实例"""
    if user_id in _user_memories:
        del _user_memories[user_id]
        logger.info(f"[Memory] Removed memory instance for user: {user_id}")

