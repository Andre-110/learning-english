"""
上下文管理服务 - 负责对话上下文的压缩和摘要
"""
from typing import List, Dict, Any, Optional
from services.llm import LLMService
from prompts.builders import PromptBuilder
from models.conversation import Message, MessageRole


class ContextManagerService:
    """上下文管理服务 - 负责管理对话上下文"""
    
    def __init__(
        self,
        llm_service: LLMService,
        prompt_builder: Optional[PromptBuilder] = None,
        summary_interval: int = 5
    ):
        self.llm_service = llm_service
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.summary_interval = summary_interval

    def should_summarize(self, current_round: int) -> bool:
        """判断是否需要生成摘要"""
        return current_round > 0 and current_round % self.summary_interval == 0

    def create_summary(
        self,
        conversation_messages: List[Message],
        current_round: int
    ) -> str:
        """
        创建对话摘要
        
        Args:
            conversation_messages: 需要摘要的消息列表
            current_round: 当前轮数
            
        Returns:
            摘要文本
        """
        # 转换为字典格式
        messages_dict = [
            {"role": msg.role.value, "content": msg.content}
            for msg in conversation_messages
        ]
        
        # 构建摘要提示词
        messages = self.prompt_builder.build_summary_prompt(
            conversation_messages=messages_dict,
            current_round=current_round
        )
        
        # 调用LLM生成摘要
        try:
            summary = self.llm_service.chat_completion(
                messages=messages,
                temperature=0.3  # 低温度以保证摘要的准确性
            )
            return summary.strip()
        except Exception as e:
            # 如果摘要失败，返回简单摘要
            return f"对话进行到第{current_round}轮，用户正在学习英语对话。错误: {str(e)}"

    def get_context_messages(
        self,
        conversation_messages: List[Message],
        summary: Optional[str] = None,
        summary_round: int = 0
    ) -> List[Message]:
        """
        获取用于LLM上下文的消息列表（包含摘要）
        
        Args:
            conversation_messages: 完整消息列表
            summary: 对话摘要
            summary_round: 摘要对应的轮数
            
        Returns:
            处理后的消息列表
        """
        context_messages = []
        
        # 如果有摘要，添加摘要消息
        if summary:
            context_messages.append(Message(
                role=MessageRole.SYSTEM,
                content=f"[对话摘要（前{summary_round}轮）]: {summary}"
            ))
        
        # 添加摘要后的消息
        start_idx = summary_round if summary else 0
        context_messages.extend(conversation_messages[start_idx:])
        
        return context_messages

