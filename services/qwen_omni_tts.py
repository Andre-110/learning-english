"""
Qwen-Omni TTS 服务 - 使用 qwen3-omni 进行文本转语音
"""
from typing import Optional
from openai import OpenAI
from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("services.qwen_omni_tts")
settings = Settings()


class QwenOmniTTSService:
    """
    Qwen-Omni TTS 服务
    
    使用 qwen3-omni 模型的音频输出功能进行 TTS
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "qwen3-omni-flash"
    ):
        self.api_key = api_key or settings.dashscope_api_key
        self.base_url = base_url or settings.dashscope_base_url
        self.model = model
        
        if not self.api_key:
            raise ValueError("DashScope API Key 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"Qwen-Omni TTS 服务初始化: model={self.model}")
    
    def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        将文本转换为语音音频
        
        Args:
            text: 要转换的文本（支持中英文）
            voice: 语音参数（qwen-omni 可能不支持此参数，保留以兼容接口）
            **kwargs: 其他参数
            
        Returns:
            音频数据（bytes）
        """
        try:
            import base64
            
            # 使用 qwen-omni 的音频输出功能
            # qwen-omni 需要同时输出文本和音频
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": text
                            }
                        ]
                    }
                ],
                modalities=["text", "audio"],  # 同时输出文本和音频
                stream=False
            )
            
            # 提取音频数据
            # qwen-omni 的响应格式：choices[0].message.content 是一个列表
            if hasattr(response, 'choices') and len(response.choices) > 0:
                message = response.choices[0].message
                
                # 检查 content 字段（可能是列表或字符串）
                if hasattr(message, 'content'):
                    content = message.content
                    
                    # 如果 content 是列表
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                # 检查是否是音频类型
                                if item.get('type') == 'audio':
                                    audio_data = item.get('audio', '')
                                    if isinstance(audio_data, str):
                                        # 可能是 base64 编码的字符串
                                        if audio_data.startswith('data:audio'):
                                            # 提取 base64 部分
                                            base64_data = audio_data.split(',')[1] if ',' in audio_data else audio_data
                                            return base64.b64decode(base64_data)
                                        else:
                                            return base64.b64decode(audio_data)
                                    elif isinstance(audio_data, bytes):
                                        return audio_data
                    
                    # 如果 content 是字符串，检查是否有音频数据
                    elif isinstance(content, str):
                        # 尝试从字符串中提取音频（如果 API 返回特殊格式）
                        pass
                
                # 检查是否有独立的 audio 字段
                if hasattr(message, 'audio'):
                    audio_data = message.audio
                    if isinstance(audio_data, str):
                        if audio_data.startswith('data:audio'):
                            base64_data = audio_data.split(',')[1] if ',' in audio_data else audio_data
                            return base64.b64decode(base64_data)
                        return base64.b64decode(audio_data)
                    elif isinstance(audio_data, bytes):
                        return audio_data
            
            # 如果无法提取音频，记录响应结构以便调试
            logger.warning(f"无法从响应中提取音频数据。响应结构: {type(response)}")
            if hasattr(response, 'choices') and len(response.choices) > 0:
                logger.warning(f"Message content: {response.choices[0].message}")
            
            raise ValueError("无法从 qwen-omni 响应中提取音频数据")
            
        except Exception as e:
            logger.error(f"Qwen-Omni TTS 生成失败: {e}")
            raise Exception(f"Qwen-Omni TTS 生成失败: {str(e)}")
    
    def list_voices(self, language: Optional[str] = None):
        """列出可用的语音列表（qwen-omni 可能不支持此功能）"""
        return []


def create_qwen_omni_tts_service(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "qwen3-omni-flash"
) -> QwenOmniTTSService:
    """创建 Qwen-Omni TTS 服务实例"""
    return QwenOmniTTSService(api_key, base_url, model)

