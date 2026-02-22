"""
阿里云 Qwen3-Omni-Flash 音频服务

使用 OpenAI 兼容接口，必须流式输出
支持音频输入和音频输出
"""
import base64
from typing import Optional, List, Dict, Any, Generator

from openai import OpenAI

from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("services.qwen_omni_audio")

settings = Settings()


class QwenOmniAudioService:
    """
    Qwen3-Omni-Flash 音频服务
    
    特点：
    - 使用 OpenAI 兼容接口
    - 必须使用流式输出 (stream=True)
    - 支持音频输入和音频输出
    - 对话连贯性更好
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        audio_model: str = "qwen3-omni-flash",
        fast_model: str = "qwen-turbo"
    ):
        self.api_key = api_key or settings.dashscope_api_key
        self.base_url = base_url or settings.dashscope_base_url
        self.audio_model = audio_model
        self.fast_model = fast_model
        
        if not self.api_key:
            raise ValueError("DashScope API Key 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"Qwen-Omni Audio 服务初始化: audio_model={self.audio_model}")
    
    def call_with_audio(
        self,
        audio_data: bytes,
        audio_format: str,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        调用 API（音频输入）- 必须使用流式，收集完整响应后返回
        """
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        messages = []
        
        # 系统提示
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # 对话历史 - Qwen-Omni 的 assistant 消息只能包含文本
        if conversation_history:
            for msg in conversation_history:
                if msg["role"] == "assistant":
                    # assistant 消息只能是文本
                    messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": msg["content"]}]
                    })
                else:
                    # user 消息可以是文本
                    messages.append({
                        "role": "user",
                        "content": [{"type": "text", "text": msg["content"]}]
                    })
        
        # 当前用户消息（音频 + 文本提示）
        user_content = [
            {
                "type": "input_audio",
                "input_audio": {
                    "data": f"data:audio/{audio_format};base64,{audio_base64}",
                    "format": audio_format
                }
            }
        ]
        if user_prompt:
            user_content.append({"type": "text", "text": user_prompt})
        
        messages.append({"role": "user", "content": user_content})
        
        logger.info(f"[API] Qwen-Omni 音频请求, 大小: {len(audio_data)} bytes")
        
        # Qwen-Omni 必须使用流式输出
        stream = self.client.chat.completions.create(
            model=self.audio_model,
            messages=messages,
            modalities=["text"],  # 只输出文本，不输出音频（TTS 单独处理）
            temperature=0.3,  # 评估轨需要稳定的JSON输出
            stream=True,
            stream_options={"include_usage": True}
        )
        
        # 收集完整响应
        full_response = ""
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
        
        return full_response
    
    def call_with_audio_stream(
        self,
        audio_data: bytes,
        audio_format: str,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        output_audio: bool = True,
        voice: str = "Cherry"
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式调用（音频输入）- 同时返回文本和音频（S2S）
        
        Yields:
            Dict with keys:
            - "text": 文本片段 (str or None)
            - "audio": 音频数据 base64 (str or None)
        """
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # S2S 模式：历史对话只在 user_prompt 中传递（作为参考信息，权重低）
        # 不在 messages 数组中传递历史对话，避免重复和高权重
        # user_prompt 中已经包含了历史对话，这里不再重复添加
        
        user_content = [
            {
                "type": "input_audio",
                "input_audio": {
                    "data": f"data:audio/{audio_format};base64,{audio_base64}",
                    "format": audio_format
                }
            }
        ]
        if user_prompt:
            user_content.append({"type": "text", "text": user_prompt})
        
        messages.append({"role": "user", "content": user_content})
        
        # 设置 modalities
        modalities = ["text", "audio"] if output_audio else ["text"]
        
        # 记录传给模型的输入（根据 output_audio 判断是交互轨还是转录轨）
        track_name = "交互轨" if output_audio else "转录轨"
        history_count = len(conversation_history) if conversation_history else 0
        logger.info(f"[{track_name}输入] System Prompt:\n{system_prompt[:200]}...")
        logger.info(f"[{track_name}输入] User Prompt (history={history_count}):\n{user_prompt[:500]}...")
        
        # 根据轨道类型设置温度：交互轨 0.8，转录轨 0.3
        temp = 0.8 if output_audio else 0.3
        
        create_params = {
            "model": self.audio_model,
            "messages": messages,
            "modalities": modalities,
            "temperature": temp,
            "stream": True,
            "stream_options": {"include_usage": True}
        }
        
        # 如果输出音频，添加 audio 参数
        if output_audio:
            create_params["audio"] = {"voice": voice, "format": "mp3"}
        
        stream = self.client.chat.completions.create(**create_params)
        
        # 收集完整响应用于日志
        full_response_text = ""
        for chunk in stream:
            result = {"text": None, "audio": None}
            
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                
                # 提取文本
                if delta.content:
                    result["text"] = delta.content
                
                # 提取音频（S2S）
                if output_audio:
                    delta_dict = delta.model_dump() if hasattr(delta, 'model_dump') else {}
                    if 'audio' in delta_dict and delta_dict['audio']:
                        audio_data = delta_dict['audio']
                        if isinstance(audio_data, dict) and 'data' in audio_data:
                            result["audio"] = audio_data['data']
            
            # 收集文本响应
            if result["text"]:
                full_response_text += result["text"]
            
            # 只有有内容时才 yield
            if result["text"] or result["audio"]:
                yield result
        
        # 记录模型返回的输出（根据 output_audio 判断是交互轨还是转录轨）
        track_name = "交互轨" if output_audio else "转录轨"
        if full_response_text:
            logger.info(f"[{track_name}输出] {full_response_text[:200]}...")
    
    def call_with_text(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        调用 API（纯文本输入）- 使用快速模型
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        messages.append({"role": "user", "content": user_prompt})
        
        response = self.client.chat.completions.create(
            model=self.fast_model,
            messages=messages,
            temperature=0.5,  # 翻译轨需要准确性
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
        流式调用（纯文本输入，纯文本输出）
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        messages.append({"role": "user", "content": user_prompt})
        
        stream = self.client.chat.completions.create(
            model=self.fast_model,
            messages=messages,
            temperature=0.5,  # 翻译轨需要准确性
            max_tokens=1000,
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def call_text_to_speech_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        voice: str = "Cherry",
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        文本输入，同时输出文本和音频（TTS 模式）
        
        使用 Qwen-Omni 模型，保持音色一致
        
        官方文档：modalities=["text", "audio"] 支持纯文本输入
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            voice: 音色选择 (Cherry, Serena, Ethan, Chelsie)
            conversation_history: 对话历史
            
        Yields:
            Dict with keys:
            - "text": 文本片段 (str or None)
            - "audio": 音频数据 base64 (str or None)
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # 纯文本输入（官方示例格式）
        messages.append({
            "role": "user", 
            "content": user_prompt
        })
        
        logger.info(f"[API] Qwen-Omni 文本转语音请求, voice={voice}")
        
        stream = self.client.chat.completions.create(
            model=self.audio_model,
            messages=messages,
            modalities=["text", "audio"],  # 输出文本+音频
            audio={"voice": voice, "format": "wav"},  # 使用 wav 格式
            temperature=1.2,  # 最高温度强制多样性
            stream=True,  # 必须流式
            stream_options={"include_usage": True}
        )
        
        for chunk in stream:
            result = {"text": None, "audio": None}
            
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                
                # 提取文本
                if delta.content:
                    result["text"] = delta.content
                
                # 提取音频
                delta_dict = delta.model_dump() if hasattr(delta, 'model_dump') else {}
                if 'audio' in delta_dict and delta_dict['audio']:
                    audio_data = delta_dict['audio']
                    if isinstance(audio_data, dict) and 'data' in audio_data:
                        result["audio"] = audio_data['data']
                    elif isinstance(audio_data, str):
                        result["audio"] = audio_data
            
            if result["text"] or result["audio"]:
                yield result


def create_qwen_omni_service(
    api_key: Optional[str] = None,
    audio_model: str = "qwen3-omni-flash",
    fast_model: str = "qwen-turbo"
) -> QwenOmniAudioService:
    """创建 Qwen-Omni 服务实例"""
    return QwenOmniAudioService(
        api_key=api_key,
        audio_model=audio_model,
        fast_model=fast_model
    )

