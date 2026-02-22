"""
提示词构建器 - 负责动态组装提示词
"""
from typing import Dict, Any, List, Optional
from .templates import (
    PromptTemplate,
    SystemPrompt,
    EvaluationPrompt,
    GenerationPrompt,
    SummaryPrompt,
    ReportPrompt
)


class PromptBuilder:
    """提示词构建器 - 负责组装完整的提示词"""

    def __init__(self):
        self.system_prompt = SystemPrompt()
        self.evaluation_prompt = EvaluationPrompt()
        self.generation_prompt = GenerationPrompt()
        self.summary_prompt = SummaryPrompt()
        self.report_prompt = ReportPrompt()

    def build_evaluation_prompt(
        self,
        conversation_history: List[Dict[str, str]],
        current_response: str,
        previous_assessments: Optional[List[Dict[str, Any]]] = None,
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        构建评估提示词
        
        Args:
            conversation_history: 对话历史
            current_response: 当前用户回答
            previous_assessments: 历史评估记录
            include_system: 是否包含系统提示词
            
        Returns:
            格式化的消息列表，可直接用于LLM API
        """
        messages = []
        
        if include_system:
            messages.append({
                "role": "system",
                "content": self.system_prompt.render()
            })
        
        evaluation_content = self.evaluation_prompt.render(
            conversation_history=conversation_history,
            current_response=current_response,
            previous_assessments=previous_assessments or []
        )
        
        messages.append({
            "role": "user",
            "content": evaluation_content
        })
        
        return messages

    def build_generation_prompt(
        self,
        ability_profile: Dict[str, Any],
        topic_pool: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        previous_topics: Optional[List[str]] = None,
        user_interests: Optional[List[Dict[str, Any]]] = None,
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        构建题目生成提示词
        
        Args:
            ability_profile: 用户能力画像
            topic_pool: 主题池
            conversation_history: 对话历史（用于连贯性）
            previous_topics: 已讨论的主题列表
            user_interests: 用户兴趣列表 [{"category": "tech", "weight": 0.8, "tags": ["AI"]}, ...]
            include_system: 是否包含系统提示词
            
        Returns:
            格式化的消息列表
        """
        messages = []
        
        if include_system:
            messages.append({
                "role": "system",
                "content": self.system_prompt.render()
            })
        
        generation_content = self.generation_prompt.render(
            ability_profile=ability_profile,
            topic_pool=topic_pool,
            conversation_history=conversation_history or [],
            previous_topics=previous_topics or [],
            user_interests=user_interests or []
        )
        
        messages.append({
            "role": "user",
            "content": generation_content
        })
        
        return messages

    def build_summary_prompt(
        self,
        conversation_messages: List[Dict[str, str]],
        current_round: int,
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        构建摘要提示词
        
        Args:
            conversation_messages: 需要摘要的消息列表
            current_round: 当前轮数
            include_system: 是否包含系统提示词
            
        Returns:
            格式化的消息列表
        """
        messages = []
        
        if include_system:
            messages.append({
                "role": "system",
                "content": self.system_prompt.render()
            })
        
        summary_content = self.summary_prompt.render(
            conversation_messages=conversation_messages,
            current_round=current_round
        )
        
        messages.append({
            "role": "user",
            "content": summary_content
        })
        
        return messages

    def build_report_prompt(
        self,
        conversation_history: List[Dict[str, str]],
        assessment_history: List[Dict[str, Any]],
        user_profile: Optional[Dict[str, Any]] = None,
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        构建报告生成提示词
        
        Args:
            conversation_history: 完整对话历史
            assessment_history: 评估历史
            user_profile: 用户画像
            include_system: 是否包含系统提示词
            
        Returns:
            格式化的消息列表
        """
        messages = []
        
        if include_system:
            messages.append({
                "role": "system",
                "content": self.system_prompt.render()
            })
        
        report_content = self.report_prompt.render(
            conversation_history=conversation_history,
            assessment_history=assessment_history,
            user_profile=user_profile
        )
        
        messages.append({
            "role": "user",
            "content": report_content
        })
        
        return messages






