"""
LLM 适配器 - 大语言模型服务

支持：
- OpenAI GPT-4o
- (未来) Qwen-Omni, Claude 等
"""
import time
from typing import Optional, List, Dict, Generator, Protocol

from openai import OpenAI

from config.settings import Settings
from config.constants import LLM_TIMEOUT
from services.utils.logger import get_logger

logger = get_logger("providers.llm")
settings = Settings()


class LLMProvider(Protocol):
    """LLM 提供者协议 - 定义统一接口"""

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Generator[str, None, None] | str:
        """
        对话生成

        Args:
            messages: 消息列表 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大 token 数
            stream: 是否流式输出

        Returns:
            如果 stream=True，返回生成器；否则返回完整回复
        """
        ...


class OpenAILLMProvider:
    """OpenAI LLM 实现 (GPT-4o)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        default_temperature: Optional[float] = None,
        default_max_tokens: Optional[int] = None
    ):
        """
        初始化 OpenAI LLM

        Args:
            api_key: API 密钥，默认从 settings 读取
            base_url: API 基础 URL，默认从 settings 读取
            model: LLM 模型，默认从 settings 读取
            default_temperature: 默认温度
            default_max_tokens: 默认最大 token
        """
        # 优先使用官方 API key，如果没有则回退到代理 key
        self.api_key = api_key or settings.openai_official_api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_official_base_url
        self.model = model or settings.pipeline_llm_model
        self.default_temperature = default_temperature or settings.pipeline_llm_temperature
        self.default_max_tokens = default_max_tokens or settings.pipeline_llm_max_tokens

        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY in .env")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=LLM_TIMEOUT
        )

        logger.info(f"[LLM] 初始化完成: model={self.model}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Generator[str, None, None] | str:
        """对话生成"""
        import time
        start_time = time.time()

        temperature = temperature or self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens

        logger.info(f"[LLM] 请求: {len(messages)} 条消息, stream={stream}")

        try:
            if stream:
                return self._chat_stream(messages, temperature, max_tokens, start_time)
            else:
                return self._chat_sync(messages, temperature, max_tokens, start_time)
        except Exception as e:
            logger.error(f"[LLM] 失败: {e}")
            raise

    def _chat_sync(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        start_time: float
    ) -> str:
        """同步调用"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        reply = response.choices[0].message.content.strip()

        elapsed = time.time() - start_time
        logger.info(f"[LLM] 完成, 耗时: {elapsed:.2f}s, 回复: {reply[:50]}...")

        return reply

    def _chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        start_time: float
    ) -> Generator[str, None, None]:
        """流式调用"""
        import time

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )

        full_reply = ""
        first_chunk = True

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                full_reply += text

                if first_chunk:
                    ttft = time.time() - start_time
                    logger.info(f"[LLM] 首字延迟 (TTFT): {ttft:.2f}s")
                    first_chunk = False

                yield text

        elapsed = time.time() - start_time
        logger.info(f"[LLM] 流式完成, 总耗时: {elapsed:.2f}s, 回复: {full_reply[:50]}...")


def create_llm_provider(provider_type: str = "openai", **kwargs) -> LLMProvider:
    """
    创建 LLM 提供者

    Args:
        provider_type: 提供者类型 ("openai", "qwen-omni")
        **kwargs: 传递给提供者的参数

    Returns:
        LLM 提供者实例
    """
    if provider_type == "openai":
        return OpenAILLMProvider(**kwargs)
    # elif provider_type == "qwen-omni":
    #     return QwenOmniLLMProvider(**kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider_type}")

