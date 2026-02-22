"""
兴趣提取服务 - 从对话中提取用户兴趣
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from services.llm import LLMService
from models.user import InterestTag
from services.utils.logger import get_logger

logger = get_logger("services.interest_extractor")


class InterestExtractorService:
    """兴趣提取服务"""
    
    # 兴趣类别定义
    INTEREST_CATEGORIES = {
        "news": ["news", "news", "current events", "headlines", "report"],
        "tech": ["technology", "tech", "AI", "software", "digital", "innovation"],
        "sports": ["sport", "football", "basketball", "athlete", "competition", "game"],
        "travel": ["travel", "trip", "vacation", "destination", "journey", "tourist"],
        "entertainment": ["movie", "music", "book", "TV", "show", "entertainment"],
        "lifestyle": ["lifestyle", "hobby", "daily", "routine", "fashion", "cooking"],
        "work": ["work", "career", "job", "business", "office", "professional"],
        "learning": ["learning", "study", "education", "course", "skill", "knowledge"]
    }
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
    
    def extract_interests_from_conversation(
        self,
        conversation_messages: List[Dict[str, str]],
        user_responses: List[str]
    ) -> List[InterestTag]:
        """
        从对话中提取用户兴趣
        
        Args:
            conversation_messages: 对话消息列表
            user_responses: 用户回答列表
            
        Returns:
            提取的兴趣标签列表
        """
        logger.info(f"[extract_interests] Extracting interests from {len(user_responses)} user responses")
        
        # 合并用户回答
        user_text = " ".join(user_responses)
        
        # 方法1: 使用关键词匹配快速提取
        interests = self._extract_by_keywords(user_text)
        
        # 方法2: 使用LLM提取更精确的兴趣（可选）
        if len(user_text) > 50:  # 只在有足够内容时使用LLM
            try:
                llm_interests = self._extract_by_llm(conversation_messages, user_responses)
                # 合并两种方法的结果
                interests = self._merge_interests(interests, llm_interests)
            except Exception as e:
                logger.warning(f"[extract_interests] LLM extraction failed: {e}, using keyword-based results")
        
        logger.info(f"[extract_interests] Extracted {len(interests)} interest categories")
        return interests
    
    def _extract_by_keywords(self, text: str) -> List[InterestTag]:
        """通过关键词匹配提取兴趣"""
        text_lower = text.lower()
        interests = []
        
        for category, keywords in self.INTEREST_CATEGORIES.items():
            matches = sum(1 for keyword in keywords if keyword in text_lower)
            if matches > 0:
                # 计算权重（基于匹配的关键词数量）
                weight = min(0.3 + (matches * 0.1), 1.0)
                
                # 提取具体标签
                tags = [kw for kw in keywords if kw in text_lower][:5]  # 最多5个标签
                
                interests.append(InterestTag(
                    category=category,
                    tags=tags,
                    weight=weight,
                    last_discussed=datetime.now().isoformat()
                ))
        
        return interests
    
    def _extract_by_llm(
        self,
        conversation_messages: List[Dict[str, str]],
        user_responses: List[str]
    ) -> List[InterestTag]:
        """使用LLM提取兴趣"""
        user_text = "\n".join([f"User: {resp}" for resp in user_responses])
        
        prompt = f"""分析以下用户对话，提取用户的兴趣标签。

用户回答：
{user_text}

请识别用户感兴趣的话题类别，从以下类别中选择：
- news: 新闻、时事
- tech: 科技、技术、AI
- sports: 体育、运动
- travel: 旅行、旅游
- entertainment: 娱乐、电影、音乐、书籍
- lifestyle: 生活方式、日常、爱好
- work: 工作、职业、商业
- learning: 学习、教育、技能

输出JSON格式：
{{
    "interests": [
        {{
            "category": "tech",
            "tags": ["AI", "programming"],
            "weight": 0.8
        }}
    ]
}}

只输出JSON，不要其他内容。"""
        
        try:
            response = self.llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            # 解析JSON响应
            import json
            import re
            
            # 提取JSON部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                interests = []
                for item in data.get("interests", []):
                    interests.append(InterestTag(
                        category=item.get("category", ""),
                        tags=item.get("tags", []),
                        weight=item.get("weight", 0.5),
                        last_discussed=datetime.now().isoformat()
                    ))
                return interests
        except Exception as e:
            logger.error(f"[extract_interests] LLM parsing failed: {e}")
        
        return []
    
    def _merge_interests(
        self,
        interests1: List[InterestTag],
        interests2: List[InterestTag]
    ) -> List[InterestTag]:
        """合并两组兴趣标签"""
        merged = {}
        
        # 合并第一组
        for interest in interests1:
            key = interest.category
            if key not in merged:
                merged[key] = interest
            else:
                # 合并标签和权重
                merged[key].tags = list(set(merged[key].tags + interest.tags))
                merged[key].weight = max(merged[key].weight, interest.weight)
        
        # 合并第二组
        for interest in interests2:
            key = interest.category
            if key not in merged:
                merged[key] = interest
            else:
                merged[key].tags = list(set(merged[key].tags + interest.tags))
                merged[key].weight = max(merged[key].weight, interest.weight)
        
        return list(merged.values())
    
    def update_user_interests(
        self,
        current_interests: List[InterestTag],
        new_interests: List[InterestTag]
    ) -> List[InterestTag]:
        """
        更新用户兴趣列表
        
        Args:
            current_interests: 当前兴趣列表
            new_interests: 新提取的兴趣列表
            
        Returns:
            更新后的兴趣列表
        """
        updated = {}
        
        # 保留现有兴趣
        for interest in current_interests:
            updated[interest.category] = interest
        
        # 更新或添加新兴趣
        for interest in new_interests:
            if interest.category in updated:
                # 更新现有兴趣
                existing = updated[interest.category]
                # 合并标签
                existing.tags = list(set(existing.tags + interest.tags))
                # 增加权重（但不超过1.0）
                existing.weight = min(existing.weight + 0.1, 1.0)
                existing.last_discussed = interest.last_discussed
            else:
                # 添加新兴趣
                updated[interest.category] = interest
        
        # 按权重排序
        result = sorted(updated.values(), key=lambda x: x.weight, reverse=True)
        
        logger.info(f"[update_user_interests] Updated interests: {len(result)} categories")
        return result

