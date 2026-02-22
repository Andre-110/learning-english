"""
评估服务 - 执行评估任务并解析结果
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from models.assessment import AssessmentResult, DimensionScore, AbilityProfile
from models.user import CEFRLevel
from models.conversation import Message, MessageRole
from services.llm import LLMService
from prompts.builders import PromptBuilder
from services.utils.logger import get_logger
from core.cefr_mapper import CEFRMapper

logger = get_logger("services.evaluator")


class EvaluatorService:
    """评估服务 - 负责执行评估任务"""
    
    def __init__(
        self,
        llm_service: LLMService,
        prompt_builder: Optional[PromptBuilder] = None
    ):
        self.llm_service = llm_service
        self.prompt_builder = prompt_builder or PromptBuilder()

    def evaluate(
        self,
        conversation_messages: List[Message],
        current_response: str,
        round_number: int,
        previous_assessments: Optional[List[Dict[str, Any]]] = None
    ) -> AssessmentResult:
        logger.info(f"[evaluate] INPUT: round={round_number}, response_length={len(current_response)}, messages_count={len(conversation_messages)}")
        logger.debug(f"[evaluate] Current response: {current_response[:200]}...")
        """
        执行评估
        
        Args:
            conversation_messages: 对话消息列表
            current_response: 当前用户回答
            round_number: 当前轮次
            previous_assessments: 历史评估记录（用于对比和趋势分析）
            
        Returns:
            评估结果
        """
        # 转换为字典格式用于提示词
        history_dict = [
            {"role": msg.role.value, "content": msg.content}
            for msg in conversation_messages
        ]
        
        # 提取历史评估记录
        if previous_assessments is None:
            previous_assessments = []
            for msg in conversation_messages:
                if msg.metadata and "assessment" in msg.metadata:
                    assess_data = msg.metadata["assessment"]
                    if isinstance(assess_data, dict):
                        previous_assessments.append({
                            "round": assess_data.get("round_number", 0),
                            "overall_score": assess_data.get("ability_profile", {}).get("overall_score", 0),
                            "cefr_level": assess_data.get("ability_profile", {}).get("cefr_level", "A1"),
                            "strengths": assess_data.get("ability_profile", {}).get("strengths", []),
                            "weaknesses": assess_data.get("ability_profile", {}).get("weaknesses", [])
                        })
        
        # 构建评估提示词
        messages = self.prompt_builder.build_evaluation_prompt(
            conversation_history=history_dict,
            current_response=current_response,
            previous_assessments=previous_assessments
        )
        
        # 调用LLM进行评估
        try:
            logger.debug(f"[evaluate] Calling LLM with {len(messages)} messages")
            response_json = self.llm_service.chat_completion_json(
                messages=messages,
                temperature=0.3  # 降低温度以提高一致性
            )
            logger.debug(f"[evaluate] LLM response received: {str(response_json)[:500]}...")
            
            # 解析评估结果
            result = self._parse_assessment_result(
                response_json=response_json,
                round_number=round_number
            )
            logger.info(f"[evaluate] OUTPUT: score={result.ability_profile.overall_score}, level={result.ability_profile.cefr_level.value}")
            return result
        except Exception as e:
            logger.error(f"[evaluate] Evaluation failed: {e}")
            # 如果评估失败，返回默认结果
            return self._create_default_assessment(round_number, str(e))

    def _parse_assessment_result(
        self,
        response_json: Dict[str, Any],
        round_number: int
    ) -> AssessmentResult:
        """解析LLM返回的评估结果"""
        # 提取维度评分
        dimension_scores = []
        for dim_data in response_json.get("dimension_scores", []):
            dimension_scores.append(DimensionScore(
                dimension=dim_data.get("dimension", ""),
                score=float(dim_data.get("score", 3.0)),
                comment=dim_data.get("comment", ""),
                reasoning=dim_data.get("reasoning")
            ))
        
        # 提取能力画像
        profile_data = response_json.get("ability_profile", {})
        overall_score = float(profile_data.get("overall_score", 50.0))
        
        # 根据分数映射CEFR等级（确保分数与等级对齐）
        llm_cefr_level = profile_data.get("cefr_level", "A1")
        mapped_cefr_level = CEFRMapper.score_to_cefr(overall_score)
        
        # 如果LLM返回的等级与分数不对齐，使用映射后的等级
        if not CEFRMapper.is_score_aligned_with_level(overall_score, CEFRLevel(llm_cefr_level)):
            logger.info(
                f"[_parse_assessment_result] CEFR level adjusted: "
                f"LLM={llm_cefr_level} -> Mapped={mapped_cefr_level.value} "
                f"(score={overall_score:.1f})"
            )
        
        ability_profile = AbilityProfile(
            overall_score=overall_score,
            cefr_level=mapped_cefr_level,  # 使用映射后的等级
            strengths=profile_data.get("strengths", []),
            weaknesses=profile_data.get("weaknesses", []),
            confidence=float(profile_data.get("confidence", 0.5))
        )
        
        return AssessmentResult(
            round_number=round_number,
            dimension_scores=dimension_scores,
            ability_profile=ability_profile,
            raw_response=response_json,
            timestamp=datetime.now().isoformat()
        )

    def _create_default_assessment(
        self,
        round_number: int,
        error_message: str
    ) -> AssessmentResult:
        """创建默认评估结果（用于错误处理）"""
        return AssessmentResult(
            round_number=round_number,
            dimension_scores=[
                DimensionScore(
                    dimension="内容相关性",
                    score=3.0,
                    comment="评估失败，使用默认值",
                    reasoning=error_message
                )
            ],
            ability_profile=AbilityProfile(
                overall_score=50.0,
                cefr_level=CEFRLevel.A1,
                strengths=[],
                weaknesses=[],
                confidence=0.0
            ),
            raw_response={"error": error_message},
            timestamp=datetime.now().isoformat()
        )


