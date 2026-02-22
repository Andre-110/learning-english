"""
对话模板服务 - 管理和选择对话模板
"""
from typing import List, Dict, Any, Optional
from models.user import CEFRLevel
from services.utils.logger import get_logger
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

logger = get_logger("services.template_service")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://uxnqqkuviqlptltcepat.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV4bnFxa3V2aXFscHRsdGNlcGF0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwODIzMDgsImV4cCI6MjA4MDY1ODMwOH0.oI7uVTWBXDnEhRgAsy_L4SZf2vGDpacwfKoEDS1DHsc")


class ConversationTemplate:
    """对话模板"""
    def __init__(self, data: Dict[str, Any]):
        self.template_id = data.get("template_id")
        self.category = data.get("category")
        self.topic_name = data.get("topic_name")
        self.cefr_level = data.get("cefr_level")
        self.template_content = data.get("template_content")
        self.keywords = data.get("keywords", [])
        self.description = data.get("description")


class TemplateService:
    """对话模板服务"""
    
    # 内置模板（作为数据库的备份）
    BUILTIN_TEMPLATES = [
        # 新闻类
        {"template_id": 1, "category": "news", "topic_name": "Technology News", "cefr_level": "B1", "template_content": "Have you heard about the latest developments in artificial intelligence? What do you think about how AI is changing our daily lives?", "keywords": ["AI", "technology"]},
        {"template_id": 2, "category": "news", "topic_name": "Environmental News", "cefr_level": "B1", "template_content": "What are your thoughts on climate change? Have you noticed any environmental changes in your area?", "keywords": ["climate", "environment"]},
        {"template_id": 3, "category": "news", "topic_name": "Health News", "cefr_level": "A2", "template_content": "Have you been following any health news recently? What do you think about the importance of exercise?", "keywords": ["health", "exercise"]},
        # 科技类
        {"template_id": 4, "category": "tech", "topic_name": "Smartphones", "cefr_level": "A2", "template_content": "What smartphone do you use? What features do you like most about it?", "keywords": ["smartphone", "mobile"]},
        {"template_id": 5, "category": "tech", "topic_name": "Social Media", "cefr_level": "B1", "template_content": "How do you use social media? What are the pros and cons of social media platforms?", "keywords": ["social media", "communication"]},
        {"template_id": 6, "category": "tech", "topic_name": "Programming", "cefr_level": "B2", "template_content": "Are you interested in programming? What programming languages do you know or want to learn?", "keywords": ["programming", "coding"]},
        # 体育类
        {"template_id": 7, "category": "sports", "topic_name": "Football", "cefr_level": "A2", "template_content": "Do you like football? Who is your favorite team or player?", "keywords": ["football", "team"]},
        {"template_id": 8, "category": "sports", "topic_name": "Fitness", "cefr_level": "A2", "template_content": "Do you exercise regularly? What kind of exercise do you prefer?", "keywords": ["fitness", "exercise"]},
        {"template_id": 9, "category": "sports", "topic_name": "Olympics", "cefr_level": "B1", "template_content": "What is your favorite Olympic sport? What do you think about the Olympic spirit?", "keywords": ["Olympics", "competition"]},
        # 旅游类
        {"template_id": 10, "category": "travel", "topic_name": "Travel Plans", "cefr_level": "A2", "template_content": "Where would you like to travel? What places are on your travel bucket list?", "keywords": ["travel", "destination"]},
        {"template_id": 11, "category": "travel", "topic_name": "Travel Experiences", "cefr_level": "B1", "template_content": "What is the most memorable trip you have taken? What made it special?", "keywords": ["travel", "experience"]},
        {"template_id": 12, "category": "travel", "topic_name": "Food", "cefr_level": "B1", "template_content": "What is your favorite cuisine? Have you tried any exotic foods while traveling?", "keywords": ["food", "cuisine"]},
        # 娱乐类
        {"template_id": 13, "category": "entertainment", "topic_name": "Movies", "cefr_level": "A2", "template_content": "What is your favorite movie? What type of movies do you enjoy?", "keywords": ["movie", "film"]},
        {"template_id": 14, "category": "entertainment", "topic_name": "Music", "cefr_level": "A2", "template_content": "What kind of music do you like? Who is your favorite artist?", "keywords": ["music", "artist"]},
        {"template_id": 15, "category": "entertainment", "topic_name": "Books", "cefr_level": "B1", "template_content": "Do you like reading? What is the best book you have read recently?", "keywords": ["book", "reading"]},
        # 生活类
        {"template_id": 16, "category": "lifestyle", "topic_name": "Daily Routine", "cefr_level": "A1", "template_content": "What is your typical day like? What time do you usually wake up?", "keywords": ["routine", "daily"]},
        {"template_id": 17, "category": "lifestyle", "topic_name": "Hobbies", "cefr_level": "A2", "template_content": "What are your hobbies? How do you spend your free time?", "keywords": ["hobby", "leisure"]},
        {"template_id": 18, "category": "lifestyle", "topic_name": "Cooking", "cefr_level": "A2", "template_content": "Do you like cooking? What is your favorite dish to make?", "keywords": ["cooking", "food"]},
        # 工作类
        {"template_id": 19, "category": "work", "topic_name": "Career", "cefr_level": "B1", "template_content": "What is your dream job? What career path are you interested in?", "keywords": ["career", "job"]},
        {"template_id": 20, "category": "work", "topic_name": "Remote Work", "cefr_level": "B2", "template_content": "What do you think about remote work? What are its advantages and disadvantages?", "keywords": ["remote work", "flexibility"]},
        # 学习类
        {"template_id": 21, "category": "learning", "topic_name": "Language Learning", "cefr_level": "B1", "template_content": "How do you learn English? What methods work best for you?", "keywords": ["language", "learning"]},
        {"template_id": 22, "category": "learning", "topic_name": "Study Tips", "cefr_level": "A2", "template_content": "What are your study habits? How do you stay motivated?", "keywords": ["study", "motivation"]},
    ]
    
    def __init__(self):
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self._cache = None
        self._use_builtin = False  # 是否使用内置模板
    
    def get_templates_by_level(
        self,
        cefr_level: str,
        category: Optional[str] = None
    ) -> List[ConversationTemplate]:
        """
        根据CEFR等级获取模板
        
        Args:
            cefr_level: CEFR等级
            category: 可选的类别筛选
            
        Returns:
            模板列表
        """
        try:
            query = self.client.table("conversation_templates").select("*").eq("cefr_level", cefr_level).eq("is_active", True)
            
            if category:
                query = query.eq("category", category)
            
            result = query.execute()
            
            templates = [ConversationTemplate(item) for item in result.data]
            logger.info(f"[get_templates_by_level] Found {len(templates)} templates for level {cefr_level}, category {category}")
            return templates
        except Exception as e:
            logger.error(f"[get_templates_by_level] Failed to fetch templates: {e}")
            return []
    
    def get_templates_by_interests(
        self,
        cefr_level: str,
        interests: List[Dict[str, Any]],
        limit: int = 5
    ) -> List[ConversationTemplate]:
        """
        根据用户兴趣获取模板
        
        Args:
            cefr_level: CEFR等级
            interests: 用户兴趣列表 [{"category": "tech", "weight": 0.8}, ...]
            limit: 返回数量限制
            
        Returns:
            推荐的模板列表
        """
        # 按权重排序兴趣
        sorted_interests = sorted(interests, key=lambda x: x.get("weight", 0), reverse=True)
        
        templates = []
        used_categories = set()
        
        # 优先选择高权重兴趣的模板
        for interest in sorted_interests[:3]:  # 只考虑前3个高权重兴趣
            category = interest.get("category")
            if category and category not in used_categories:
                category_templates = self.get_templates_by_level(cefr_level, category)
                templates.extend(category_templates[:2])  # 每个类别最多2个模板
                used_categories.add(category)
        
        # 如果模板不够，补充其他类别的模板
        if len(templates) < limit:
            all_templates = self.get_templates_by_level(cefr_level)
            for template in all_templates:
                if template.category not in used_categories and len(templates) < limit:
                    templates.append(template)
        
        logger.info(f"[get_templates_by_interests] Selected {len(templates)} templates based on interests")
        return templates[:limit]
    
    def get_random_template(
        self,
        cefr_level: str,
        exclude_categories: Optional[List[str]] = None
    ) -> Optional[ConversationTemplate]:
        """
        随机获取一个模板
        
        Args:
            cefr_level: CEFR等级
            exclude_categories: 排除的类别列表
            
        Returns:
            随机模板
        """
        try:
            query = self.client.table("conversation_templates").select("*").eq("cefr_level", cefr_level).eq("is_active", True)
            
            result = query.execute()
            
            templates = [ConversationTemplate(item) for item in result.data]
            
            # 排除指定类别
            if exclude_categories:
                templates = [t for t in templates if t.category not in exclude_categories]
            
            if templates:
                import random
                return random.choice(templates)
            
            return None
        except Exception as e:
            logger.error(f"[get_random_template] Failed: {e}")
            return None
    
    def get_template_by_id(self, template_id: int) -> Optional[ConversationTemplate]:
        """根据ID获取模板"""
        try:
            result = self.client.table("conversation_templates").select("*").eq("template_id", template_id).execute()
            if result.data:
                return ConversationTemplate(result.data[0])
            return None
        except Exception as e:
            logger.error(f"[get_template_by_id] Failed: {e}")
            return None

