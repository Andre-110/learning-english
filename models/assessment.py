"""
评估模型 - 定义评估结果和维度评分
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .user import CEFRLevel


class DimensionScore(BaseModel):
    """维度评分"""
    dimension: str = Field(..., description="评估维度名称")
    score: float = Field(..., ge=1.0, le=5.0, description="评分 1-5分")
    comment: str = Field(..., description="评语")
    reasoning: Optional[str] = Field(default=None, description="评分理由")


class AbilityProfile(BaseModel):
    """能力画像（评估后更新）"""
    overall_score: float = Field(..., ge=0.0, le=100.0, description="综合分数 0-100")
    cefr_level: CEFRLevel = Field(..., description="推断的CEFR等级")
    strengths: List[str] = Field(default_factory=list, description="强项")
    weaknesses: List[str] = Field(default_factory=list, description="弱项")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="评估置信度")


class AssessmentResult(BaseModel):
    """单轮评估结果"""
    round_number: int = Field(..., description="评估轮次")
    dimension_scores: List[DimensionScore] = Field(..., description="各维度评分")
    ability_profile: AbilityProfile = Field(..., description="更新后的能力画像")
    raw_response: Optional[Dict[str, Any]] = Field(default=None, description="LLM原始响应（用于调试）")
    timestamp: str = Field(..., description="评估时间戳")






