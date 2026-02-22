"""
OpenRouter Audio 服务 - 纯 API 调用层

职责：
- 调用 OpenRouter GPT-4o Audio API
- 处理音频输入/输出
- 不管理 prompt（从 prompts/templates.py 获取）
"""
import base64
import time
from typing import Optional, List, Dict, Any, Generator

from openai import OpenAI

from config.llm_config import llm_config
from services.utils.logger import get_logger

logger = get_logger("services.openrouter_audio")


class OpenRouterAudioService:
    """
    OpenRouter Audio 服务 - 纯 API 调用
    
    只负责：
    1. 调用 OpenRouter API
    2. 处理音频格式
    3. 返回原始响应
    
    不负责：
    - Prompt 构建（由 unified_processor 处理）
    - 响应解析（由 unified_processor 处理）
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        audio_model: str = "openai/gpt-4o-audio-preview",
        fast_model: str = "openai/gpt-4o-mini"
    ):
        self.api_key = api_key or llm_config.get_openrouter_api_key()
        self.base_url = llm_config.get_openrouter_base_url()
        self.audio_model = audio_model
        self.fast_model = fast_model
        
        if not self.api_key:
            raise ValueError("OpenRouter API Key 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers={
                "HTTP-Referer": "https://usergenie.ai",
                "X-Title": "LinguaCoach"
            }
        )
        
        logger.info(f"OpenRouter Audio 服务初始化: model={audio_model}")
    
    def call_with_audio(
        self,
        audio_data: bytes,
        audio_format: str,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        调用 API（音频输入）
        
        Args:
            audio_data: 音频二进制数据
            audio_format: 音频格式 (wav, mp3)
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            conversation_history: 对话历史
            
        Returns:
            LLM 响应文本
        """
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        # 用户消息（音频 + 文本提示）
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": audio_base64,
                        "format": audio_format
                    }
                },
                {"type": "text", "text": user_prompt}
            ]
        })
        
        logger.info(f"[API] 发送音频请求, 大小: {len(audio_data)} bytes")
        
        response = self.client.chat.completions.create(
            model=self.audio_model,
            messages=messages,
            modalities=["text"],  # 只需要文本输出，TTS 单独处理
            temperature=0.7,
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    
    def call_with_audio_stream(
        self,
        audio_data: bytes,
        audio_format: str,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[str, None, None]:
        """
        流式调用 API（音频输入）
        
        Yields:
            响应文本片段
        """
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": audio_base64,
                        "format": audio_format
                    }
                },
                {"type": "text", "text": user_prompt}
            ]
        })
        
        logger.info(f"[API] 流式请求, 音频大小: {len(audio_data)} bytes")
        
        stream = self.client.chat.completions.create(
            model=self.audio_model,
            messages=messages,
            modalities=["text"],  # 只需要文本输出
            temperature=0.7,
            max_tokens=1500,
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def call_with_text(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        调用 API（纯文本输入）
        
        用于标准流程（STT 后的文本处理）
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        messages.append({"role": "user", "content": user_prompt})
        
        response = self.client.chat.completions.create(
            model=self.fast_model,
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
    
    def call_with_text_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[str, None, None]:
        """
        流式调用 API（纯文本输入）
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        messages.append({"role": "user", "content": user_prompt})
        
        stream = self.client.chat.completions.create(
            model=self.fast_model,
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# 工厂函数
def create_openrouter_service(
    api_key: Optional[str] = None,
    audio_model: str = "openai/gpt-4o-audio-preview",
    fast_model: str = "openai/gpt-4o-mini"
) -> OpenRouterAudioService:
    """创建 OpenRouter 服务实例"""
    return OpenRouterAudioService(
        api_key=api_key,
        audio_model=audio_model,
        fast_model=fast_model
    )
