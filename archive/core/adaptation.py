"""
自适应引擎 - 实现IRT自适应逻辑（通过提示词工程）
"""
from typing import Dict, Any
from models.user import UserProfile
from models.assessment import AssessmentResult


class AdaptationEngine:
    """自适应引擎 - 实现动态适配逻辑"""
    
    def calculate_difficulty_adjustment(
        self,
        current_profile: UserProfile,
        assessment_result: AssessmentResult
    ) -> Dict[str, Any]:
        """
        计算难度调整（模拟IRT题目选择逻辑）
        
        基于用户表现动态调整下一题的难度
        """
        current_score = assessment_result.ability_profile.overall_score
        current_level = assessment_result.ability_profile.cefr_level
        
        # 简单的自适应逻辑：根据表现调整难度
        # 如果表现好（>80分），可以适当提升难度
        # 如果表现差（<60分），可以适当降低难度
        
        if current_score >= 80:
            # 表现优秀，可以挑战更高一级
            suggested_level = self._get_next_level(current_level)
            adjustment = "increase"
        elif current_score < 60:
            # 表现不佳，可以降低一级
            suggested_level = self._get_previous_level(current_level)
            adjustment = "decrease"
        else:
            # 表现适中，保持当前水平
            suggested_level = current_level
            adjustment = "maintain"
        
        return {
            "suggested_level": suggested_level.value,
            "adjustment": adjustment,
            "reasoning": f"Current score: {current_score}, Level: {current_level.value}"
        }
    
    def _get_next_level(self, level):
        """获取下一级CEFR等级"""
        from models.user import CEFRLevel
        levels = [CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1, CEFRLevel.B2, CEFRLevel.C1, CEFRLevel.C2]
        try:
            idx = levels.index(level)
            return levels[min(idx + 1, len(levels) - 1)]
        except ValueError:
            return level
    
    def _get_previous_level(self, level):
        """获取上一级CEFR等级"""
        from models.user import CEFRLevel
        levels = [CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1, CEFRLevel.B2, CEFRLevel.C1, CEFRLevel.C2]
        try:
            idx = levels.index(level)
            return levels[max(idx - 1, 0)]
        except ValueError:
            return level






