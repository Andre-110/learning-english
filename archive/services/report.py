"""
学习报告生成服务 - 生成学习建议和规划报告
"""
from typing import List, Dict, Any, Optional
from services.llm import LLMService
from prompts.builders import PromptBuilder
from models.user import UserProfile
from models.conversation import Conversation, Message
from models.assessment import AssessmentResult
from services.utils.logger import get_logger

logger = get_logger("services.report")


class ReportService:
    """学习报告生成服务"""
    
    def __init__(
        self,
        llm_service: LLMService,
        prompt_builder: Optional[PromptBuilder] = None
    ):
        self.llm_service = llm_service
        self.prompt_builder = prompt_builder or PromptBuilder()

    def generate_learning_report(
        self,
        conversation: Conversation,
        user_profile: UserProfile,
        assessment_history: List[AssessmentResult]
    ) -> str:
        """
        生成学习建议和规划报告
        
        Args:
            conversation: 对话对象
            user_profile: 用户画像
            assessment_history: 评估历史
            
        Returns:
            学习报告文本（Markdown格式）
        """
        logger.info(f"[generate_learning_report] Generating report for user {user_profile.user_id}")
        
        # 转换为字典格式
        conversation_history = [
            {"role": msg.role.value, "content": msg.content}
            for msg in conversation.messages
        ]
        
        assessment_history_dict = []
        for assess in assessment_history:
            assessment_history_dict.append({
                "round": assess.round_number,
                "overall_score": assess.ability_profile.overall_score,
                "cefr_level": assess.ability_profile.cefr_level.value,
                "strengths": assess.ability_profile.strengths,
                "weaknesses": assess.ability_profile.weaknesses,
                "dimension_scores": [
                    {
                        "dimension": dim.dimension,
                        "score": dim.score,
                        "comment": dim.comment
                    }
                    for dim in assess.dimension_scores
                ]
            })
        
        user_profile_dict = user_profile.dict()
        
        # 构建报告提示词
        messages = self.prompt_builder.build_report_prompt(
            conversation_history=conversation_history,
            assessment_history=assessment_history_dict,
            user_profile=user_profile_dict
        )
        
        # 调用LLM生成报告
        try:
            logger.debug(f"[generate_learning_report] Calling LLM to generate report")
            report = self.llm_service.chat_completion(
                messages=messages,
                temperature=0.7  # 适中的温度以平衡创造性和准确性
            )
            report = report.strip()
            logger.info(f"[generate_learning_report] Report generated successfully, length: {len(report)}")
            return report
        except Exception as e:
            logger.error(f"[generate_learning_report] Report generation failed: {e}")
            # 返回默认报告
            return self._create_default_report(user_profile, assessment_history)

    def _create_default_report(
        self,
        user_profile: UserProfile,
        assessment_history: List[AssessmentResult]
    ) -> str:
        """创建默认报告（用于错误处理）"""
        latest_assess = assessment_history[-1] if assessment_history else None
        
        report = f"""# 学习评估报告

## 能力分析
- **综合分数**: {user_profile.overall_score}/100
- **CEFR等级**: {user_profile.cefr_level.value}
- **对话轮数**: {user_profile.conversation_count}

## 强弱项分析
- **强项**: {', '.join(user_profile.strengths) if user_profile.strengths else '待观察'}
- **弱项**: {', '.join(user_profile.weaknesses) if user_profile.weaknesses else '待观察'}

## 学习建议
基于您的当前水平，建议：
1. 继续练习日常对话
2. 关注语法准确性
3. 扩大词汇量
4. 提高表达流利度

## 学习规划
- **短期目标**: 巩固当前CEFR等级的基础能力
- **中期目标**: 提升到下一CEFR等级
- **长期目标**: 达到流利交流水平

*注：此报告为系统自动生成，建议结合专业教师指导使用。*
"""
        return report

