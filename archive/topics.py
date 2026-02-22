"""
主题池配置 - 按CEFR等级分类的话题库
"""
from typing import List, Dict, Any
from pydantic import BaseModel
from models.user import CEFRLevel


class Topic(BaseModel):
    """主题定义"""
    name: str
    description: str
    cefr_level: CEFRLevel
    keywords: List[str] = []


class TopicPool:
    """主题池 - 管理按CEFR等级分类的话题"""
    
    def __init__(self):
        self.topics = self._initialize_topics()
    
    def _initialize_topics(self) -> List[Topic]:
        """初始化主题池"""
        return [
            # A1级别
            Topic(
                name="自我介绍",
                description="Basic self-introduction and personal information",
                cefr_level=CEFRLevel.A1,
                keywords=["introduction", "name", "age", "hobby"]
            ),
            Topic(
                name="日常活动",
                description="Daily routines and simple activities",
                cefr_level=CEFRLevel.A1,
                keywords=["daily", "routine", "activity", "simple"]
            ),
            Topic(
                name="食物偏好",
                description="Favorite foods and basic food preferences",
                cefr_level=CEFRLevel.A1,
                keywords=["food", "favorite", "preference"]
            ),
            
            # A2级别
            Topic(
                name="周末计划",
                description="Weekend plans and activities",
                cefr_level=CEFRLevel.A2,
                keywords=["weekend", "plan", "activity"]
            ),
            Topic(
                name="旅行经历",
                description="Travel experiences and destinations",
                cefr_level=CEFRLevel.A2,
                keywords=["travel", "trip", "destination"]
            ),
            Topic(
                name="兴趣爱好",
                description="Hobbies and interests in detail",
                cefr_level=CEFRLevel.A2,
                keywords=["hobby", "interest", "leisure"]
            ),
            
            # B1级别
            Topic(
                name="环保生活",
                description="Environmental protection and sustainable living",
                cefr_level=CEFRLevel.B1,
                keywords=["environment", "green", "sustainable"]
            ),
            Topic(
                name="工作与职业",
                description="Work, career, and professional development",
                cefr_level=CEFRLevel.B1,
                keywords=["work", "career", "job", "profession"]
            ),
            Topic(
                name="健康生活",
                description="Health, fitness, and lifestyle choices",
                cefr_level=CEFRLevel.B1,
                keywords=["health", "fitness", "lifestyle"]
            ),
            
            # B2级别
            Topic(
                name="人工智能影响",
                description="Impact of artificial intelligence on society",
                cefr_level=CEFRLevel.B2,
                keywords=["AI", "artificial intelligence", "technology", "society"]
            ),
            Topic(
                name="教育系统",
                description="Education systems and learning methods",
                cefr_level=CEFRLevel.B2,
                keywords=["education", "learning", "system"]
            ),
            Topic(
                name="全球化",
                description="Globalization and cultural exchange",
                cefr_level=CEFRLevel.B2,
                keywords=["globalization", "culture", "exchange"]
            ),
            
            # C1级别
            Topic(
                name="经济与政策",
                description="Economic policies and their social implications",
                cefr_level=CEFRLevel.C1,
                keywords=["economy", "policy", "social"]
            ),
            Topic(
                name="科技伦理",
                description="Ethical considerations in technology development",
                cefr_level=CEFRLevel.C1,
                keywords=["ethics", "technology", "moral"]
            ),
            
            # C2级别
            Topic(
                name="哲学思辨",
                description="Philosophical discussions and abstract thinking",
                cefr_level=CEFRLevel.C2,
                keywords=["philosophy", "abstract", "thinking"]
            ),
            Topic(
                name="复杂社会问题",
                description="Complex social issues and multi-perspective analysis",
                cefr_level=CEFRLevel.C2,
                keywords=["social", "complex", "analysis"]
            ),
        ]
    
    def get_topics_by_level(self, cefr_level: str) -> List[Dict[str, Any]]:
        """根据CEFR等级获取主题列表"""
        level = CEFRLevel(cefr_level) if isinstance(cefr_level, str) else cefr_level
        matching_topics = [t for t in self.topics if t.cefr_level == level]
        
        # 转换为字典格式用于提示词
        return [
            {
                "name": t.name,
                "description": t.description,
                "cefr_level": t.cefr_level.value,
                "keywords": t.keywords
            }
            for t in matching_topics
        ]
    
    def get_all_topics(self) -> List[Dict[str, Any]]:
        """获取所有主题"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "cefr_level": t.cefr_level.value,
                "keywords": t.keywords
            }
            for t in self.topics
        ]






