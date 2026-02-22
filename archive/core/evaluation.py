"""
评估引擎 - 协调评估流程（可扩展为更复杂的评估逻辑）
"""
from typing import List
from models.assessment import AssessmentResult
from services.evaluator import EvaluatorService


class EvaluationEngine:
    """评估引擎 - 负责协调评估流程"""
    
    def __init__(self, evaluator_service: EvaluatorService):
        self.evaluator_service = evaluator_service

    def evaluate_round(
        self,
        conversation_messages,
        current_response: str,
        round_number: int
    ) -> AssessmentResult:
        """执行单轮评估"""
        return self.evaluator_service.evaluate(
            conversation_messages=conversation_messages,
            current_response=current_response,
            round_number=round_number
        )

    def batch_evaluate(self, assessment_results: List[AssessmentResult]) -> dict:
        """批量评估分析（可用于报告生成）"""
        if not assessment_results:
            return {}
        
        avg_score = sum(r.ability_profile.overall_score for r in assessment_results) / len(assessment_results)
        level_distribution = {}
        
        for result in assessment_results:
            level = result.ability_profile.cefr_level.value
            level_distribution[level] = level_distribution.get(level, 0) + 1
        
        return {
            "average_score": avg_score,
            "level_distribution": level_distribution,
            "total_rounds": len(assessment_results)
        }






