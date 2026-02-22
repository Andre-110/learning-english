"""
Search 适配器 - 网络搜索服务

支持：
- OpenAI Responses API (web_search_preview)
"""
from typing import Optional, Protocol

from openai import OpenAI

from config.settings import Settings
from config.constants import HOT_CONTENT_SEARCH_TIMEOUT
from services.utils.logger import get_logger

logger = get_logger("providers.search")
settings = Settings()


class SearchProvider(Protocol):
    """Search 提供者协议 - 定义统一接口"""

    def search(self, query: str) -> str:
        """
        执行网络搜索

        Args:
            query: 搜索查询

        Returns:
            搜索结果文本
        """
        ...


class OpenAISearchProvider:
    """OpenAI Search 实现 (web_search_preview)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o"
    ):
        """
        初始化 OpenAI Search

        Args:
            api_key: API 密钥，默认从 settings 读取
            base_url: API 基础 URL，默认使用官方端点
            model: 使用的模型
        """
        # web_search 必须使用官方 API key 和端点
        self.api_key = api_key or settings.openai_official_api_key or settings.openai_api_key
        self.base_url = "https://api.openai.com/v1"
        self.model = model

        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY in .env")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=HOT_CONTENT_SEARCH_TIMEOUT
        )

        logger.info(f"[Search] 初始化完成: model={self.model}")

    def search(self, query: str) -> str:
        """执行网络搜索"""
        import time
        start_time = time.time()

        logger.info(f"[Search] 搜索: {query[:50]}...")

        try:
            search_input = (
                f"Search for: {query}\n\n"
                "Find ONE interesting fact or story that's FUN to chat about.\n"
                "AVOID: politics, disasters, controversies, technical jargon.\n"
                "PREFER: fun facts, entertainment, lifestyle, feel-good stories.\n"
                "Return a 2-3 sentence summary with the source."
            )

            response = self.client.responses.create(
                model=self.model,
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
            logger.info(f"[Search] 完成, 耗时: {elapsed:.2f}s, 结果长度: {len(result)}")

            return result

        except Exception as e:
            logger.error(f"[Search] 失败: {e}")
            return ""


# 工厂函数
def create_search_provider(provider_type: str = "openai", **kwargs) -> SearchProvider:
    """
    创建 Search 提供者

    Args:
        provider_type: 提供者类型 ("openai")
        **kwargs: 传递给提供者的参数

    Returns:
        Search 提供者实例
    """
    if provider_type == "openai":
        return OpenAISearchProvider(**kwargs)
    else:
        raise ValueError(f"Unknown Search provider: {provider_type}")

