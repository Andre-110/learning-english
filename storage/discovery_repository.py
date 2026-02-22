"""
每日发现模块的数据存储实现

数据表设计：
1. discovery_articles - 存储生成的文章
2. discovery_interactions - 存储用户与文章的交互（对话、测验）
3. user_vocabulary - 用户生词本
"""
from typing import Optional, Dict, List
from datetime import datetime
from supabase import Client
from services.utils.logger import get_logger
import json
from storage.impl.supabase_repository import get_supabase_client

logger = get_logger("storage.discovery")


class DiscoveryRepository:
    """每日发现数据存储"""
    
    def __init__(self):
        self.client: Client = get_supabase_client()
        self._ensure_tables()
    
    def _ensure_tables(self):
        """确保表存在（通过尝试查询来检测）"""
        # 注意：实际生产环境应该通过 Supabase Dashboard 或迁移脚本创建表
        # 这里只是检测表是否存在
        try:
            self.client.table("discovery_articles").select("id").limit(1).execute()
        except Exception as e:
            logger.warning(f"discovery_articles 表可能不存在: {e}")
    
    # ========== 文章存储 ==========
    
    def save_article(self, user_id: str, article_data: dict) -> str:
        """
        保存生成的文章
        
        Args:
            user_id: 用户ID
            article_data: 文章数据（包含 title, simplified_content, original_content, vocabulary, quiz 等）
        
        Returns:
            article_id: 文章ID
        """
        import uuid
        article_id = str(uuid.uuid4())
        
        data = {
            "id": article_id,
            "user_id": user_id,
            "title": article_data.get("title", ""),
            "topic": article_data.get("topic", ""),
            "custom_topic": article_data.get("custom_topic"),
            "cefr_level": article_data.get("cefr_level", "B1"),
            "simplified_content": json.dumps(article_data.get("simplified_content", []), ensure_ascii=False),
            "original_content": json.dumps(article_data.get("original_content", []), ensure_ascii=False),
            "vocabulary": json.dumps(article_data.get("vocabulary", []), ensure_ascii=False),
            "quiz": json.dumps(article_data.get("quiz"), ensure_ascii=False) if article_data.get("quiz") else None,
            "grammar_focus": json.dumps(article_data.get("grammar_focus"), ensure_ascii=False) if article_data.get("grammar_focus") else None,
            "source": article_data.get("source", ""),
            "created_at": datetime.now().isoformat()
        }
        
        try:
            self.client.table("discovery_articles").insert(data).execute()
            logger.info(f"[Discovery] 保存文章: {article_id}, 标题: {article_data.get('title', '')[:30]}")
            return article_id
        except Exception as e:
            logger.error(f"[Discovery] 保存文章失败: {e}")
            return None
    
    def get_article(self, article_id: str) -> Optional[dict]:
        """获取文章详情"""
        try:
            result = self.client.table("discovery_articles").select("*").eq("id", article_id).execute()
            if result.data:
                article = result.data[0]
                # 解析 JSON 字段
                article["simplified_content"] = json.loads(article.get("simplified_content") or "[]")
                article["original_content"] = json.loads(article.get("original_content") or "[]")
                article["vocabulary"] = json.loads(article.get("vocabulary") or "[]")
                article["quiz"] = json.loads(article.get("quiz")) if article.get("quiz") else None
                article["grammar_focus"] = json.loads(article.get("grammar_focus")) if article.get("grammar_focus") else None
                return article
        except Exception as e:
            logger.error(f"[Discovery] 获取文章失败: {e}")
        return None
    
    def get_user_articles(self, user_id: str, limit: int = 20) -> List[dict]:
        """获取用户的历史文章列表"""
        try:
            result = self.client.table("discovery_articles")\
                .select("id, title, topic, custom_topic, cefr_level, created_at")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            return result.data or []
        except Exception as e:
            logger.error(f"[Discovery] 获取用户文章列表失败: {e}")
            return []
    
    # ========== 交互记录存储 ==========
    
    def save_interaction(self, user_id: str, article_id: str, interaction_type: str, content: dict):
        """
        保存用户与文章的交互
        
        Args:
            user_id: 用户ID
            article_id: 文章ID
            interaction_type: 交互类型 ('chat', 'quiz', 'voice_chat', 'reading')
            content: 交互内容
        """
        import uuid
        
        data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "article_id": article_id,
            "interaction_type": interaction_type,
            "content": json.dumps(content, ensure_ascii=False),
            "created_at": datetime.now().isoformat()
        }
        
        try:
            self.client.table("discovery_interactions").insert(data).execute()
            logger.info(f"[Discovery] 保存交互: {interaction_type}")
        except Exception as e:
            logger.error(f"[Discovery] 保存交互失败: {e}")
    
    def get_article_interactions(self, article_id: str) -> List[dict]:
        """获取文章的所有交互记录"""
        try:
            result = self.client.table("discovery_interactions")\
                .select("*")\
                .eq("article_id", article_id)\
                .order("created_at", desc=False)\
                .execute()
            
            interactions = []
            for item in result.data or []:
                item["content"] = json.loads(item.get("content") or "{}")
                interactions.append(item)
            return interactions
        except Exception as e:
            logger.error(f"[Discovery] 获取交互记录失败: {e}")
            return []
    
    # ========== 生词本 ==========
    
    def add_vocabulary(self, user_id: str, word_data: dict) -> bool:
        """
        添加单词到生词本
        
        Args:
            user_id: 用户ID
            word_data: 单词数据 {word, phonetic, definition, example_sentence, source_article_id}
        """
        import uuid
        
        # 检查是否已存在
        existing = self.get_vocabulary_word(user_id, word_data.get("word", ""))
        if existing:
            # 更新复习次数
            self._update_vocabulary_review(existing["id"])
            return True
        
        data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "word": word_data.get("word", ""),
            "phonetic": word_data.get("phonetic", ""),
            "definition": word_data.get("definition", ""),
            "example_sentence": word_data.get("example_sentence", ""),
            "source_article_id": word_data.get("source_article_id"),
            "mastery_level": 0,  # 0: 新词, 1: 认识, 2: 熟悉, 3: 掌握
            "review_count": 0,
            "created_at": datetime.now().isoformat(),
            "last_reviewed_at": None
        }
        
        try:
            self.client.table("user_vocabulary").insert(data).execute()
            logger.info(f"[Discovery] 添加生词: {word_data.get('word')}")
            return True
        except Exception as e:
            logger.error(f"[Discovery] 添加生词失败: {e}")
            return False
    
    def get_vocabulary_word(self, user_id: str, word: str) -> Optional[dict]:
        """获取用户的某个生词"""
        try:
            result = self.client.table("user_vocabulary")\
                .select("*")\
                .eq("user_id", user_id)\
                .eq("word", word)\
                .execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[Discovery] 获取生词失败: {e}")
            return None
    
    def get_user_vocabulary(self, user_id: str, mastery_level: int = None, limit: int = 100) -> List[dict]:
        """
        获取用户的生词本
        
        Args:
            user_id: 用户ID
            mastery_level: 筛选掌握程度（可选）
            limit: 返回数量限制
        """
        try:
            query = self.client.table("user_vocabulary")\
                .select("*")\
                .eq("user_id", user_id)
            
            if mastery_level is not None:
                query = query.eq("mastery_level", mastery_level)
            
            result = query.order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"[Discovery] 获取生词本失败: {e}")
            return []
    
    def update_vocabulary_mastery(self, vocabulary_id: str, mastery_level: int):
        """更新单词掌握程度"""
        try:
            self.client.table("user_vocabulary")\
                .update({
                    "mastery_level": mastery_level,
                    "last_reviewed_at": datetime.now().isoformat()
                })\
                .eq("id", vocabulary_id)\
                .execute()
        except Exception as e:
            logger.error(f"[Discovery] 更新掌握程度失败: {e}")
    
    def _update_vocabulary_review(self, vocabulary_id: str):
        """更新单词复习记录"""
        try:
            # 先获取当前 review_count
            result = self.client.table("user_vocabulary")\
                .select("review_count")\
                .eq("id", vocabulary_id)\
                .execute()
            
            current_count = result.data[0].get("review_count", 0) if result.data else 0
            
            self.client.table("user_vocabulary")\
                .update({
                    "review_count": current_count + 1,
                    "last_reviewed_at": datetime.now().isoformat()
                })\
                .eq("id", vocabulary_id)\
                .execute()
        except Exception as e:
            logger.error(f"[Discovery] 更新复习记录失败: {e}")
    
    def remove_vocabulary(self, user_id: str, word: str) -> bool:
        """从生词本移除单词"""
        try:
            self.client.table("user_vocabulary")\
                .delete()\
                .eq("user_id", user_id)\
                .eq("word", word)\
                .execute()
            return True
        except Exception as e:
            logger.error(f"[Discovery] 移除生词失败: {e}")
            return False


# 全局单例
_repository = None

def get_discovery_repository() -> DiscoveryRepository:
    """获取 DiscoveryRepository 单例"""
    global _repository
    if _repository is None:
        _repository = DiscoveryRepository()
    return _repository

