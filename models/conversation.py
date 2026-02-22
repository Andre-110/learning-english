"""
对话模型 - 定义对话会话和消息结构
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ConversationState(str, Enum):
    """对话状态"""
    INITIALIZING = "initializing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"


class Message(BaseModel):
    """单条消息"""
    role: MessageRole = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据（如评估结果等）")


class Conversation(BaseModel):
    """对话会话"""
    conversation_id: str = Field(..., description="会话唯一标识")
    user_id: str = Field(..., description="用户ID")
    messages: List[Message] = Field(default_factory=list, description="消息列表")
    state: ConversationState = Field(default=ConversationState.INITIALIZING, description="会话状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    summary: Optional[str] = Field(default=None, description="对话摘要（用于上下文压缩）")
    summary_round: int = Field(default=0, description="摘要对应的轮数")

    def add_message(self, role: MessageRole, content: str, metadata: Optional[Dict[str, Any]] = None):
        """添加消息"""
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.messages.append(message)
        self.updated_at = datetime.now()

    def get_recent_messages(self, count: int = 10) -> List[Message]:
        """获取最近N条消息"""
        return self.messages[-count:] if len(self.messages) > count else self.messages

    def get_messages_for_context(self, include_summary: bool = True) -> List[Message]:
        """获取用于LLM上下文的消息列表（包含摘要）"""
        context_messages = []
        if include_summary and self.summary:
            context_messages.append(Message(
                role=MessageRole.SYSTEM,
                content=f"[对话摘要（前{self.summary_round}轮）]: {self.summary}"
            ))
        # 添加摘要后的消息
        start_idx = self.summary_round if self.summary else 0
        context_messages.extend(self.messages[start_idx:])
        return context_messages






