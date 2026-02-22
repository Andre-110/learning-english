"""
用户模型 - 定义用户能力画像和CEFR等级
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class CEFRLevel(str, Enum):
    """CEFR等级枚举"""
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class InterestTag(BaseModel):
    """兴趣标签"""
    category: str = Field(..., description="兴趣类别：news, tech, sports, travel, entertainment, lifestyle, work, learning")
    tags: List[str] = Field(default_factory=list, description="具体标签列表")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="兴趣权重 0-1")
    last_discussed: Optional[str] = Field(default=None, description="最后讨论时间")


class UserProfile(BaseModel):
    """用户能力画像"""
    user_id: str = Field(..., description="用户唯一标识")
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0, description="综合能力分数 0-100")
    cefr_level: CEFRLevel = Field(default=CEFRLevel.A1, description="当前CEFR等级")
    strengths: List[str] = Field(default_factory=list, description="强项列表")
    weaknesses: List[str] = Field(default_factory=list, description="弱项列表")
    interests: List[InterestTag] = Field(default_factory=list, description="兴趣标签列表")
    conversation_count: int = Field(default=0, description="对话轮数")
    last_updated: Optional[str] = Field(default=None, description="最后更新时间")
    
    # 🆕 朋友式交流增强字段
    display_name: Optional[str] = Field(default=None, description="用户昵称/显示名")
    last_conversation_topic: Optional[str] = Field(default=None, description="上次对话主题")
    last_conversation_date: Optional[str] = Field(default=None, description="上次对话时间")
    memorable_moments: List[str] = Field(default_factory=list, description="印象深刻的话题/故事（最多5个）")

    def update_from_assessment(self, assessment_result: "AssessmentResult"):
        """根据评估结果更新画像"""
        self.overall_score = assessment_result.ability_profile.overall_score
        self.cefr_level = assessment_result.ability_profile.cefr_level
        self.strengths = assessment_result.ability_profile.strengths
        self.weaknesses = assessment_result.ability_profile.weaknesses
        self.conversation_count += 1






