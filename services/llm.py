"""
LLM服务 - 统一的LLM调用接口，支持多种提供商
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from enum import Enum
import json
from openai import OpenAI
from anthropic import Anthropic
from config.llm_config import llm_config


class LLMProvider(str, Enum):
    """LLM提供商枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMService(ABC):
    """LLM服务抽象接口"""
    
    @abstractmethod
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """发送聊天请求并返回响应"""
        pass

    @abstractmethod
    def chat_completion_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        **kwargs
    ) -> Dict[str, Any]:
        """发送聊天请求并返回JSON格式响应"""
        pass


class OpenAIService(LLMService):
    """OpenAI服务实现"""
    
    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None, base_url: Optional[str] = None):
        # 使用全局配置（可通过参数覆盖）
        api_key = api_key or llm_config.get_openai_api_key()
        base_url = base_url or llm_config.get_openai_base_url()
        default_model = default_model or llm_config.get_primary_model()
        
        # 创建OpenAI客户端
        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = OpenAI(api_key=api_key)
        
        self.default_model = default_model

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """发送聊天请求"""
        response = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
            **kwargs
        )
        return response.choices[0].message.content

    def chat_completion_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        **kwargs
    ) -> Dict[str, Any]:
        """发送聊天请求并解析JSON响应"""
        # 在消息中添加强制JSON输出要求
        json_messages = messages.copy()
        if json_messages and json_messages[-1]["role"] == "user":
            json_messages[-1]["content"] += "\n\n请确保输出是有效的JSON格式，不要包含任何额外的文本或markdown代码块标记。"
        
        model_name = model or self.default_model
        
        # 准备请求参数
        request_kwargs = {
            "model": model_name,
            "messages": json_messages,
            "temperature": temperature,
            **kwargs
        }
        
        # 只有支持JSON模式的模型才设置response_format
        # GPT-4和GPT-3.5-turbo-1106+支持JSON模式
        if model_name.startswith("gpt-4") or ("gpt-3.5-turbo" in model_name and "1106" in model_name):
            request_kwargs["response_format"] = {"type": "json_object"}
        
        response = self.client.chat.completions.create(**request_kwargs)
        response_text = response.choices[0].message.content
        
        # 尝试解析JSON
        try:
            # 移除可能的markdown代码块标记
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()
            
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            # 如果解析失败，返回错误信息
            return {"error": "Failed to parse JSON", "raw_response": response_text}


class AnthropicService(LLMService):
    """Anthropic服务实现"""
    
    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        # 使用全局配置（可通过参数覆盖）
        api_key = api_key or llm_config.get_anthropic_api_key()
        default_model = default_model or llm_config.get_primary_model()
        
        self.client = Anthropic(api_key=api_key)
        self.default_model = default_model

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """发送聊天请求"""
        # Anthropic API格式略有不同
        system_message = None
        conversation_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                conversation_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        response = self.client.messages.create(
            model=model or self.default_model,
            system=system_message or "",
            messages=conversation_messages,
            temperature=temperature,
            max_tokens=4096,
            **kwargs
        )
        
        return response.content[0].text

    def chat_completion_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        **kwargs
    ) -> Dict[str, Any]:
        """发送聊天请求并解析JSON响应"""
        json_messages = messages.copy()
        if json_messages and json_messages[-1]["role"] == "user":
            json_messages[-1]["content"] += "\n\n请确保输出是有效的JSON格式，不要包含任何额外的文本或markdown代码块标记。"
        
        response_text = self.chat_completion(
            messages=json_messages,
            model=model or self.default_model,
            temperature=temperature,
            **kwargs
        )
        
        try:
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()
            
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            return {"error": "Failed to parse JSON", "raw_response": response_text}


# 默认服务实例
_default_service: Optional[LLMService] = None


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024
) -> str:
    """
    便捷函数：调用 LLM 并返回结果
    
    Args:
        system_prompt: 系统提示词
        user_prompt: 用户输入
        model: 模型名称（可选，默认使用配置中的模型）
        temperature: 温度参数
        max_tokens: 最大 token 数
        
    Returns:
        LLM 的回复文本
    """
    global _default_service
    
    if _default_service is None:
        _default_service = LLMServiceFactory.create()
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    return _default_service.chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )


class LLMServiceFactory:
    """LLM服务工厂"""
    
    @staticmethod
    def create(provider: Optional[LLMProvider] = None, **kwargs) -> LLMService:
        """
        创建LLM服务实例
        
        Args:
            provider: LLM提供商（如果不提供，使用全局配置）
            **kwargs: 其他参数（api_key, default_model, base_url等）
        """
        # 使用全局配置或传入的provider
        if provider is None:
            provider_str = llm_config.get_provider()
            provider = LLMProvider(provider_str)
        
        if provider == LLMProvider.OPENAI:
            # 如果没有显式传入base_url，使用全局配置
            if "base_url" not in kwargs:
                kwargs["base_url"] = llm_config.get_openai_base_url()
            # 如果没有显式传入default_model，使用全局配置
            if "default_model" not in kwargs:
                kwargs["default_model"] = llm_config.get_primary_model()
            return OpenAIService(**kwargs)
        elif provider == LLMProvider.ANTHROPIC:
            # 如果没有显式传入default_model，使用全局配置
            if "default_model" not in kwargs:
                kwargs["default_model"] = llm_config.get_primary_model()
            return AnthropicService(**kwargs)
        else:
            raise ValueError(f"Unsupported provider: {provider}")


