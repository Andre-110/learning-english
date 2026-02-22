"""
热点内容注入服务 - Content Injector

功能：
1. 根据用户兴趣搜索实时热点内容（使用 OpenAI Responses API + web_search）
2. 将内容改写为适合用户 CEFR 等级的英文
3. 提供开场白热点和被动触发热点两种模式

架构：
- 异步执行，不阻塞交互轨
- 使用 OpenAI 官方 API（web_search_preview 不支持代理）
- 内容缓存，避免重复搜索
"""
import time
import random
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from openai import OpenAI
from services.utils.logger import get_logger
from config.settings import Settings

logger = get_logger("services.content_injector")
settings = Settings()


def _get_openai_api_key() -> str:
    """获取 OpenAI API Key（优先使用官方 key）"""
    # 统一使用官方 key（可走 yunwu 代理）
    api_key = settings.openai_official_api_key or settings.openai_api_key
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, content injection will be disabled")
        return ""
    return api_key


# CEFR 等级描述（用于内容改写）
LEVEL_DESCRIPTIONS = {
    "A1": "very simple vocabulary (100-500 words), short sentences (5-8 words), basic present tense only",
    "A2": "simple vocabulary (500-1000 words), short sentences (8-12 words), present and past tense",
    "B1": "intermediate vocabulary (1000-2000 words), moderate complexity (12-18 words), common idioms",
    "B2": "upper-intermediate vocabulary (2000-4000 words), complex sentences (15-25 words), varied grammar",
    "C1": "advanced vocabulary (4000-8000 words), sophisticated structures, nuanced expressions",
    "C2": "native-level vocabulary, complex academic language, subtle nuances"
}

# 通用热门话题（当用户没有明确兴趣时使用）
GENERAL_TOPICS = [
    "interesting science discoveries",
    "fun facts about the world",
    "trending technology news",
    "popular movies and TV shows",
    "amazing travel destinations",
    "health and wellness tips",
    "inspiring stories",
    "cultural events around the world"
]

@dataclass
class HotContent:
    """热点内容数据结构"""
    topic: str              # 话题
    headline: str           # 标题/要点（英文，已适配等级）
    detail: str             # 详细内容（英文，已适配等级）
    source: str             # 来源
    fetched_at: datetime    # 获取时间
    cefr_level: str         # 适配的等级


class ContentInjector:
    """
    热点内容注入服务

    使用方式：
    1. 开场白：fetch_for_greeting() - 获取适合暖场的热点
    2. 被动触发：fetch_for_topic() - 根据用户提到的话题搜索
    3. 缓存预热：warmup_cache() - 后台预热通用话题缓存
    """

    def __init__(self):
        """初始化 - 使用 OpenAI 官方 API（从环境变量读取配置）"""
        api_key = _get_openai_api_key()
        self.enabled = bool(api_key)
        self.client = OpenAI(
            api_key=api_key or "dummy",  # 避免 OpenAI 客户端报错
            base_url=settings.openai_official_base_url or llm_config.get_openai_base_url() or "https://api.openai.com/v1"
        ) if api_key else None

        # 简单的内存缓存（topic -> HotContent）
        self._cache: Dict[str, HotContent] = {}
        self._cache_ttl = timedelta(hours=1)  # 缓存 1 小时
        
        logger.info("[ContentInjector] 初始化完成")

    def _get_cached(self, topic: str) -> Optional[HotContent]:
        """检查缓存"""
        if topic in self._cache:
            content = self._cache[topic]
            if datetime.now() - content.fetched_at < self._cache_ttl:
                logger.info(f"[ContentInjector] 缓存命中: {topic}")
                return content
            else:
                del self._cache[topic]
        return None

    def _set_cache(self, topic: str, content: HotContent):
        """设置缓存"""
        self._cache[topic] = content
        # 简单的缓存清理：超过 50 个就清理最旧的
        if len(self._cache) > 50:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].fetched_at)
            del self._cache[oldest_key]

    def _search_web(self, query: str) -> str:
        """
        使用 OpenAI Responses API + web_search 搜索内容

        Returns:
            搜索结果文本
        """
        start_time = time.time()
        logger.info(f"[ContentInjector] 搜索: {query}")

        try:
            search_input = (
                f"Search for: {query}\n\n"
                "Find ONE interesting fact or recent story that would be FUN to chat about.\n"
                "AVOID: politics, disasters, controversies, technical jargon, sad news.\n"
                "PREFER: fun facts, cultural moments, entertainment, lifestyle, feel-good stories.\n"
                "Return a 2-3 sentence summary with the source. Keep it light and conversational."
            )
            response = self.client.responses.create(
                model="gpt-4o",
                tools=[{"type": "web_search_preview"}],
                input=search_input
            )

            # 提取结果
            result = ""
            if isinstance(response, str):
                result = response
            else:
                for output in response.output:
                    if hasattr(output, 'content'):
                        for content in output.content:
                            if hasattr(content, 'text'):
                                result = content.text
                                break

            elapsed = time.time() - start_time
            logger.info(f"[ContentInjector] 搜索完成, 耗时: {elapsed:.2f}s, 结果长度: {len(result)}")
            return result

        except Exception as e:
            logger.error(f"[ContentInjector] 搜索失败: {e}")
            return ""

    def _adapt_content(self, raw_content: str, cefr_level: str, for_greeting: bool = False) -> Dict[str, str]:
        """
        将原始内容改写为适合用户等级的英文

        Args:
            raw_content: 原始搜索结果
            cefr_level: 用户 CEFR 等级
            for_greeting: 是否用于开场白（更短更口语化）

        Returns:
            {"headline": "...", "detail": "...", "source": "..."}
        """
        level_desc = LEVEL_DESCRIPTIONS.get(cefr_level, LEVEL_DESCRIPTIONS["B1"])

        if for_greeting:
            # 开场白：更短、更口语化、以问题结尾
            prompt = f"""Transform this content into something a friend might casually mention in conversation.

ORIGINAL:
{raw_content[:1000]}

TARGET: CEFR {cefr_level} learner
Level: {level_desc}

IMAGINE: You just read something interesting and want to share it naturally with a friend learning English.

OUTPUT (JSON only):
{{
    "headline": "A fun one-liner you'd actually say to a friend (under 12 words)",
    "detail": "How you'd naturally share this - like texting a friend. End with a casual question. (under 35 words)",
    "source": "Source if known"
}}

VIBE:
- Sound like a real person, not a news anchor
- "Hey, did you know..." or "I just read that..." style
- Simple question at the end to keep chatting
- Match {cefr_level} vocabulary naturally"""
        else:
            # 被动触发：用户提到某话题时自然引入
            prompt = f"""The user just mentioned a topic. You found something interesting to share.

ORIGINAL CONTENT:
{raw_content[:1500]}

TARGET: CEFR {cefr_level} learner
Level: {level_desc}

CONTEXT: User brought up this topic in conversation. You want to add something interesting without lecturing.

OUTPUT (JSON only):
{{
    "headline": "Quick hook - what makes this interesting (under 12 words)",
    "detail": "Share like you're telling a friend something cool you learned. Natural, not educational. Can ask what they think. (under 50 words)",
    "source": "Source if known"
}}

TONE:
- "Oh that reminds me..." or "You know what's cool about that?" style
- Share enthusiasm, not information
- Match {cefr_level} vocabulary naturally
- Invite their thoughts, don't quiz them"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an English tutor. Output valid JSON only, no markdown."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300,
                response_format={"type": "json_object"}
            )

            import json
            result = json.loads(response.choices[0].message.content.strip())
            return result

        except Exception as e:
            logger.error(f"[ContentInjector] 内容改写失败: {e}")
            return {"headline": "", "detail": "", "source": ""}

    def fetch_for_greeting(
        self,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Optional[HotContent]:
        """
        获取适合开场白的热点内容（同步方法）

        Args:
            user_profile: 用户画像（包含 interests 和 cefr_level）

        Returns:
            HotContent 或 None
        """
        # 确定话题：优先用户兴趣，否则随机通用话题
        interests = []
        cefr_level = "B1"

        if user_profile:
            cefr_level = user_profile.get('cefr_level', 'B1')
            raw_interests = user_profile.get('interests', [])
            if isinstance(raw_interests, list):
                interests = [i for i in raw_interests if isinstance(i, str)]

        if interests:
            # 随机选一个用户兴趣
            topic = random.choice(interests)
            search_query = f"latest news about {topic}"
        else:
            # 随机选一个通用话题
            topic = random.choice(GENERAL_TOPICS)
            search_query = topic

        logger.info(f"[ContentInjector] 开场白话题: {topic}, 等级: {cefr_level}")

        # 检查缓存
        cache_key = f"greeting_{topic}_{cefr_level}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # 搜索内容
        raw_content = self._search_web(search_query)
        if not raw_content:
            return None

        # 改写适配等级
        adapted = self._adapt_content(raw_content, cefr_level, for_greeting=True)
        if not adapted.get("detail"):
            return None

        # 构建结果
        content = HotContent(
            topic=topic,
            headline=adapted.get("headline", ""),
            detail=adapted.get("detail", ""),
            source=adapted.get("source", ""),
            fetched_at=datetime.now(),
            cefr_level=cefr_level
        )

        # 缓存
        self._set_cache(cache_key, content)

        logger.info(f"[ContentInjector] 开场白内容: {content.headline}")
        return content

    def fetch_for_topic(
        self,
        topic: str,
        cefr_level: str = "B1"
    ) -> Optional[HotContent]:
        """
        根据话题搜索热点内容（同步方法）

        Args:
            topic: 用户提到的话题
            cefr_level: 用户 CEFR 等级

        Returns:
            HotContent 或 None
        """
        logger.info(f"[ContentInjector] 被动触发: {topic}, 等级: {cefr_level}")

        # 检查缓存
        cache_key = f"topic_{topic}_{cefr_level}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # 搜索内容
        search_query = f"latest interesting news about {topic}"
        raw_content = self._search_web(search_query)
        if not raw_content:
            return None

        # 改写适配等级
        adapted = self._adapt_content(raw_content, cefr_level, for_greeting=False)
        if not adapted.get("detail"):
            return None

        # 构建结果
        content = HotContent(
            topic=topic,
            headline=adapted.get("headline", ""),
            detail=adapted.get("detail", ""),
            source=adapted.get("source", ""),
            fetched_at=datetime.now(),
            cefr_level=cefr_level
        )

        # 缓存
        self._set_cache(cache_key, content)

        logger.info(f"[ContentInjector] 话题内容: {content.headline}")
        return content

    async def fetch_for_greeting_async(
        self,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Optional[HotContent]:
        """异步版本的开场白热点获取"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.fetch_for_greeting, user_profile)

    async def fetch_for_topic_async(
        self,
        topic: str,
        cefr_level: str = "B1"
    ) -> Optional[HotContent]:
        """异步版本的话题热点获取"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.fetch_for_topic(topic, cefr_level))


# 全局单例
_injector: Optional[ContentInjector] = None


def get_content_injector() -> ContentInjector:
    """获取 ContentInjector 单例"""
    global _injector
    if _injector is None:
        _injector = ContentInjector()
    return _injector

