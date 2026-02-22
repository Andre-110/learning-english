"""
热点轨 (Hot Content Track)

职责：搜索 + 改写 + 注入热点内容
特点：异步执行，可选功能

流程：
1. 触发条件：
   - 开场白：根据用户兴趣获取热点
   - 被动触发：用户提到相关话题时
2. 搜索：使用 OpenAI web_search_preview
3. 改写：根据用户 CEFR 等级调整难度
4. 注入：在下一轮对话中自然融入

缓存策略：
- TTL: 1 小时
- 最大条目: 50
"""
import asyncio
import random
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from providers import create_search_provider, create_llm_provider
from config.constants import (
    HOT_CONTENT_CACHE_TTL_HOURS,
    HOT_CONTENT_CACHE_MAX_SIZE,
    HOT_CONTENT_GREETING_TIMEOUT,
    HOT_CONTENT_SEARCH_TIMEOUT,
    GENERAL_HOT_TOPICS,
)
from services.utils.logger import get_logger

logger = get_logger("tracks.hot_content")


@dataclass
class HotContent:
    """热点内容"""
    topic: str
    headline: str
    detail: str
    source: str = ""
    cefr_level: str = "B1"
    fetched_at: datetime = None

    def __post_init__(self):
        if self.fetched_at is None:
            self.fetched_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "headline": self.headline,
            "detail": self.detail,
            "source": self.source,
            "cefr_level": self.cefr_level,
        }

    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() - self.fetched_at > timedelta(hours=HOT_CONTENT_CACHE_TTL_HOURS)


class HotContentTrack:
    """
    热点轨 - 搜索 + 改写 + 注入

    支持两种触发模式：
    1. 开场白热点：fetch_for_greeting()
    2. 被动触发热点：fetch_for_topic()
    """

    def __init__(
        self,
        search_provider=None,
        llm_provider=None
    ):
        """
        初始化热点轨

        Args:
            search_provider: 搜索提供者
            llm_provider: LLM 提供者（用于内容改写）
        """
        self.search = search_provider or create_search_provider()
        self.llm = llm_provider or create_llm_provider()

        # 内存缓存
        self._cache: Dict[str, HotContent] = {}

        logger.info("[热点轨] 初始化完成")

    async def fetch_for_greeting(
        self,
        topic: Optional[str] = None,
        cefr_level: str = "B1"
    ) -> Optional[HotContent]:
        """
        获取开场白热点

        Args:
            topic: 话题（用户兴趣），如果为空则使用通用热点
            cefr_level: 用户 CEFR 等级

        Returns:
            HotContent 或 None
        """
        # 选择话题
        if not topic:
            topic = random.choice(GENERAL_HOT_TOPICS)

        logger.info(f"[热点轨] 获取开场白热点: {topic}")

        # 检查缓存
        cache_key = f"greeting:{topic}:{cefr_level}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                logger.info(f"[热点轨] 命中缓存: {cached.headline}")
                return cached

        try:
            return await asyncio.wait_for(
                self._fetch_and_adapt(topic, cefr_level, cache_key),
                timeout=HOT_CONTENT_GREETING_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"[热点轨] 开场白热点超时: {topic}")
            return None
        except Exception as e:
            logger.error(f"[热点轨] 获取开场白热点失败: {e}")
            return None

    async def fetch_for_topic(
        self,
        topic: str,
        cefr_level: str = "B1"
    ) -> Optional[HotContent]:
        """
        获取被动触发热点（用户提到某话题时）

        Args:
            topic: 话题（用户兴趣）
            cefr_level: 用户 CEFR 等级

        Returns:
            HotContent 或 None
        """
        logger.info(f"[热点轨] 获取话题热点: {topic}")

        # 检查缓存
        cache_key = f"topic:{topic}:{cefr_level}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                logger.info(f"[热点轨] 命中缓存: {cached.headline}")
                return cached

        try:
            return await asyncio.wait_for(
                self._fetch_and_adapt(topic, cefr_level, cache_key),
                timeout=HOT_CONTENT_SEARCH_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"[热点轨] 话题热点超时: {topic}")
            return None
        except Exception as e:
            logger.error(f"[热点轨] 获取话题热点失败: {e}")
            return None

    async def _fetch_and_adapt(
        self,
        topic: str,
        cefr_level: str,
        cache_key: str
    ) -> Optional[HotContent]:
        """
        搜索并改写热点内容
        """
        loop = asyncio.get_event_loop()

        # 1. 搜索 - 强调对话性内容
        search_query = f"interesting facts or fun news about {topic}"
        raw_result = await loop.run_in_executor(
            None,
            lambda: self.search.search(search_query)
        )

        if not raw_result:
            logger.warning(f"[热点轨] 搜索无结果: {topic}")
            return None

        # 2. 改写
        adapted = await loop.run_in_executor(
            None,
            lambda: self._adapt_content(raw_result, topic, cefr_level)
        )

        if not adapted:
            return None

        # 3. 缓存
        hot_content = HotContent(
            topic=topic,
            headline=adapted.get("headline", ""),
            detail=adapted.get("detail", ""),
            source=adapted.get("source", ""),
            cefr_level=cefr_level,
        )

        self._cache[cache_key] = hot_content
        self._cleanup_cache()

        logger.info(f"[热点轨] 成功获取: {hot_content.headline}")
        return hot_content

    def _adapt_content(
        self,
        raw_content: str,
        topic: str,
        cefr_level: str
    ) -> Optional[Dict[str, str]]:
        """
        根据 CEFR 等级改写内容
        """
        import json

        level_desc = {
            "A1": "very simple words, short sentences, basic vocabulary only",
            "A2": "simple words, short sentences, common vocabulary",
            "B1": "clear language, moderate vocabulary, some complex sentences",
            "B2": "natural language, varied vocabulary, complex sentences allowed",
            "C1": "sophisticated language, advanced vocabulary, nuanced expressions",
            "C2": "native-like language, idiomatic expressions, any complexity",
        }

        prompt = f"""Turn this into something you'd casually share with a friend who's learning English.

Content:
{raw_content[:1000]}

Target: {cefr_level} level learner
Style: {level_desc.get(cefr_level, level_desc['B1'])}

Return JSON:
{{
    "headline": "A fun hook - like how you'd start telling a friend (under 12 words)",
    "detail": "Share it naturally, like chatting. End with a simple question to keep talking. (under 40 words)",
    "source": "Source if mentioned"
}}

Sound like a real person sharing something cool, not a news report. JSON only."""

        messages = [
            {"role": "system", "content": "You adapt news for language learners. Output only JSON."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = self.llm.chat(messages, temperature=0.5, max_tokens=300, stream=False)

            # 清理 JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
                response = response.strip()

            return json.loads(response)

        except Exception as e:
            logger.error(f"[热点轨] 内容改写失败: {e}")
            return None

    def _cleanup_cache(self):
        """清理过期和超量缓存"""
        # 清理过期
        expired_keys = [
            k for k, v in self._cache.items()
            if v.is_expired()
        ]
        for k in expired_keys:
            del self._cache[k]

        # 清理超量（LRU）
        if len(self._cache) > HOT_CONTENT_CACHE_MAX_SIZE:
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: x[1].fetched_at
            )
            for k, _ in sorted_items[:len(self._cache) - HOT_CONTENT_CACHE_MAX_SIZE]:
                del self._cache[k]

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "size": len(self._cache),
            "max_size": HOT_CONTENT_CACHE_MAX_SIZE,
            "ttl_hours": HOT_CONTENT_CACHE_TTL_HOURS,
        }


# 单例
_hot_content_track: Optional[HotContentTrack] = None


def get_hot_content_track() -> HotContentTrack:
    """获取热点轨单例"""
    global _hot_content_track
    if _hot_content_track is None:
        _hot_content_track = HotContentTrack()
    return _hot_content_track

