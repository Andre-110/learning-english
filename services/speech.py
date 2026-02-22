"""
语音服务 - 处理语音转文本
"""
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO
from openai import OpenAI
from config.llm_config import llm_config


class SpeechService(ABC):
    """语音服务抽象接口"""
    
    @abstractmethod
    def transcribe_audio(self, audio_file: BinaryIO, language: Optional[str] = None) -> str:
        """将音频转换为文本"""
        pass


class WhisperService(SpeechService):
    """使用OpenAI Whisper API的语音服务"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        import os
        
        # 使用全局配置（可通过参数覆盖）
        api_key = api_key or llm_config.get_openai_api_key()
        base_url = base_url or llm_config.get_openai_base_url()
        
        # 可以通过环境变量WHISPER_BASE_URL指定Whisper专用代理
        # 否则使用配置的base_url（yunwu.ai支持Whisper API）
        whisper_base_url = os.getenv("WHISPER_BASE_URL") or base_url
        
        if whisper_base_url:
            # 确保base_url格式正确（需要/v1后缀）
            if not whisper_base_url.endswith("/v1"):
                whisper_base_url = whisper_base_url.rstrip("/") + "/v1"
            # 使用http_client参数避免httpx兼容性问题
            import httpx
            http_client = httpx.Client(
                base_url=whisper_base_url,
                timeout=60.0,
                follow_redirects=True
            )
            self.client = OpenAI(api_key=api_key, http_client=http_client)
            self.base_url = whisper_base_url
        else:
            # 如果没有配置，使用官方OpenAI API
            self.client = OpenAI(api_key=api_key)
            self.base_url = None
        
        # 保存配置用于错误处理
        self.api_key = api_key
    
    def transcribe_audio(
        self,
        audio_file: BinaryIO,
        language: Optional[str] = None
    ) -> str:
        """
        使用Whisper API转录音频
        
        Args:
            audio_file: 音频文件对象
            language: 可选，指定语言代码（如'zh', 'en'）
            
        Returns:
            转录的文本
        """
        try:
            # 重置文件指针到开头
            audio_file.seek(0)
            
            # 调用Whisper API
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,  # None表示自动检测
                response_format="text"
            )
            
            # 检查返回的是否是HTML（说明代理不支持）
            if isinstance(transcript, str) and transcript.strip().startswith('<!DOCTYPE'):
                # 如果base_url是代理且不支持Whisper，尝试使用官方API
                if self.base_url and self.base_url != "https://api.openai.com/v1":
                    raise Exception(
                        f"代理服务 {self.base_url} 可能不支持Whisper API。"
                        "请使用官方OpenAI API或支持Whisper的代理服务。"
                    )
            
            return transcript.strip() if isinstance(transcript, str) else str(transcript).strip()
        except Exception as e:
            error_msg = str(e)
            # 如果是代理不支持的错误，提供更清晰的提示
            if "multipart" in error_msg.lower() or "invalid_audio_request" in error_msg.lower():
                if self.base_url and "yunwu.ai" in self.base_url:
                    raise Exception(
                        f"语音转录失败: yunwu.ai代理可能不支持Whisper API。"
                        "建议：1) 使用官方OpenAI API（删除OPENAI_BASE_URL配置）"
                        "或 2) 使用支持Whisper的代理服务。"
                        f"原始错误: {error_msg}"
                    )
            raise Exception(f"语音转录失败: {error_msg}")


class SpeechServiceFactory:
    """语音服务工厂"""
    
    @staticmethod
    def create(provider: str = "whisper", **kwargs) -> SpeechService:
        """
        创建语音服务实例
        
        Args:
            provider: 语音服务提供商
                - "whisper": OpenAI Whisper API（云端）
                - "funasr": FunASR/SenseVoice（本地部署）
                - "doubao": 豆包大模型 ASR（中文优化）
            **kwargs: 其他参数
                - whisper: api_key, base_url
                - funasr: model_dir, model_name, language, use_itn
                - doubao: app_key, access_key, language
        """
        if provider == "whisper":
            # 如果没有显式传入base_url，使用全局配置
            if "base_url" not in kwargs:
                kwargs["base_url"] = llm_config.get_openai_base_url()
            return WhisperService(**kwargs)
        elif provider == "funasr":
            from services.funasr_service import FunASRService
            return FunASRService(**kwargs)
        elif provider == "doubao":
            from services.doubao_asr import DoubaoASRService, DoubaoASRConfig
            config = DoubaoASRConfig(
                app_key=kwargs.get("app_key", ""),
                access_key=kwargs.get("access_key", ""),
                language=kwargs.get("language", "zh-CN")
            )
            return DoubaoASRService(config)
        else:
            raise ValueError(
                f"Unsupported speech provider: {provider}. "
                "Supported providers: 'whisper' (API), 'funasr' (local), 'doubao' (Chinese optimized)"
            )

