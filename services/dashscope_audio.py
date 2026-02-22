"""
阿里云 DashScope 音频服务

音频调用：使用 DashScope 原生 SDK (MultiModalConversation)
文本调用：使用 OpenAI 兼容接口

支持流式输出
"""
import base64
from typing import Optional, List, Dict, Any, Generator

import dashscope
from dashscope import MultiModalConversation
from openai import OpenAI

from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("services.dashscope_audio")

settings = Settings()


class DashScopeAudioService:
    """
    阿里云 DashScope 音频服务
    
    - 音频调用：使用原生 SDK (MultiModalConversation)
    - 文本调用：使用 OpenAI 兼容接口
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        audio_model: Optional[str] = None,
        fast_model: Optional[str] = None
    ):
        self.api_key = api_key or settings.dashscope_api_key
        self.base_url = settings.dashscope_base_url
        self.audio_model = audio_model or settings.dashscope_audio_model
        self.fast_model = fast_model or settings.dashscope_fast_model
        
        if not self.api_key:
            raise ValueError("DashScope API Key 未配置")
        
        # 设置 DashScope 原生 SDK 的 API Key（用于音频调用）
        dashscope.api_key = self.api_key
        
        # 创建 OpenAI 兼容客户端（用于文本调用）
        self.openai_client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"DashScope Audio 服务初始化: audio_model={self.audio_model}, fast_model={self.fast_model}")
    
    def call_with_audio(
        self,
        audio_data: bytes,
        audio_format: str,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        非流式调用（音频输入）
        
        使用 DashScope 原生 SDK 的 MultiModalConversation
        """
        # 构建消息
        messages = []
        
        # 系统提示
        if system_prompt:
            messages.append({
                "role": "system",
                "content": [{"text": system_prompt}]
            })
        
        # 对话历史
        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}]
                })
        
        # 用户消息（音频 + 文本）
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        user_content = [
            {"audio": f"data:audio/{audio_format};base64,{audio_base64}"},
        ]
        if user_prompt:
            user_content.append({"text": user_prompt})
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        logger.info(f"[API] 发送音频请求, 大小: {len(audio_data)} bytes")
        
        response = MultiModalConversation.call(
            model=self.audio_model,
            messages=messages,
            result_format="message"
        )
        
        # 解析响应
        if response.status_code == 200:
            content = response.output.choices[0].message.content
            if isinstance(content, list) and len(content) > 0:
                return content[0].get("text", "")
            return str(content)
        else:
            raise Exception(f"DashScope API 错误: {response.code} - {response.message}")
    
    def call_with_audio_stream(
        self,
        audio_data: bytes,
        audio_format: str,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[str, None, None]:
        """
        流式调用（音频输入）- 真正的流式输出
        """
        # 构建消息
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": [{"text": system_prompt}]
            })
        
        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}]
                })
        
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        user_content = [
            {"audio": f"data:audio/{audio_format};base64,{audio_base64}"},
        ]
        if user_prompt:
            user_content.append({"text": user_prompt})
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        logger.info(f"[API] 流式请求, 音频大小: {len(audio_data)} bytes")
        
        # 流式调用
        responses = MultiModalConversation.call(
            model=self.audio_model,
            messages=messages,
            result_format="message",
            stream=True,
            incremental_output=True
        )
        
        for response in responses:
            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if isinstance(content, list) and len(content) > 0:
                    text = content[0].get("text", "")
                    if text:
                        yield text
            else:
                logger.error(f"流式响应错误: {response.code} - {response.message}")
    
    def call_with_text(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        非流式调用（纯文本输入）- 使用 OpenAI 兼容接口
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        messages.append({"role": "user", "content": user_prompt})
        
        response = self.openai_client.chat.completions.create(
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
        流式调用（纯文本输入）- 使用 OpenAI 兼容接口
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        messages.append({"role": "user", "content": user_prompt})
        
        stream = self.openai_client.chat.completions.create(
            model=self.fast_model,
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def create_dashscope_service(
    api_key: Optional[str] = None,
    audio_model: Optional[str] = None,
    fast_model: Optional[str] = None
) -> DashScopeAudioService:
    """创建 DashScope 服务实例"""
    return DashScopeAudioService(
        api_key=api_key,
        audio_model=audio_model,
        fast_model=fast_model
    )
