"""
文本转语音（TTS）服务 - 支持多种TTS提供商
"""
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO, List, Dict
import io
import asyncio
import edge_tts
from openai import OpenAI
from config.llm_config import llm_config


class TTSService(ABC):
    """TTS服务抽象接口"""
    
    @abstractmethod
    def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> bytes:
        """将文本转换为语音音频"""
        pass
    
    @abstractmethod
    def list_voices(self, language: Optional[str] = None) -> List[Dict]:
        """列出可用的语音列表"""
        pass


class EdgeTTSService(TTSService):
    """使用 Microsoft Edge TTS 的服务"""
    
    def __init__(
        self,
        default_voice: Optional[str] = None,
        default_rate: str = "+0%",
        default_volume: str = "+0%",
        default_pitch: str = "+0Hz"
    ):
        """
        初始化 Edge TTS 服务
        
        Args:
            default_voice: 默认语音（如 'en-US-JennyNeural'）
            default_rate: 默认语速（如 '+0%', '-50%'）
            default_volume: 默认音量（如 '+0%', '-50%'）
            default_pitch: 默认音调（如 '+0Hz', '-50Hz'）
        """
        self.default_voice = default_voice
        self.default_rate = default_rate
        self.default_volume = default_volume
        self.default_pitch = default_pitch
    
    async def _text_to_speech_async(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> bytes:
        """
        异步将文本转换为语音音频
        
        Args:
            text: 要转换的文本
            voice: 语音名称（如 'en-US-JennyNeural'）
            rate: 语速（如 '+0%', '-50%'）
            volume: 音量（如 '+0%', '-50%'）
            pitch: 音调（如 '+0Hz', '-50Hz'）
            
        Returns:
            音频数据（bytes）
        """
        # 使用默认值（确保不是 None）
        voice = voice or self.default_voice
        rate = rate if rate is not None else self.default_rate
        volume = volume if volume is not None else self.default_volume
        pitch = pitch if pitch is not None else self.default_pitch
        
        # 如果没有指定语音，使用英语默认语音
        if not voice:
            # 尝试获取英语女性语音（Jenny）
            try:
                voices = await edge_tts.list_voices()
                # 优先选择 en-US-JennyNeural
                for v in voices:
                    if v.get('ShortName') == 'en-US-JennyNeural':
                        voice = 'en-US-JennyNeural'
                        break
                # 如果没找到，选择第一个英语语音
                if not voice:
                    for v in voices:
                        if v.get('Locale', '').startswith('en-'):
                            voice = v.get('ShortName')
                            break
                # 如果还是没找到，使用第一个
                if not voice and voices:
                    voice = voices[0].get('ShortName')
            except Exception:
                # 如果获取语音列表失败，使用默认值
                voice = 'en-US-JennyNeural'
        
        # 确保所有参数都不是 None（edge-tts 不接受 None）
        if rate is None:
            rate = "+0%"
        if volume is None:
            volume = "+0%"
        if pitch is None:
            pitch = "+0Hz"
        
        # 构建通信对象
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
        
        # 生成音频数据
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        return audio_data
    
    def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> bytes:
        """
        将文本转换为语音音频（同步接口）
        
        注意：在 FastAPI 异步环境中，应该直接使用 _text_to_speech_async
        
        Args:
            text: 要转换的文本
            voice: 语音名称（如 'en-US-JennyNeural'）
            rate: 语速（如 '+0%', '-50%'）
            volume: 音量（如 '+0%', '-50%'）
            pitch: 音调（如 '+0Hz', '-50Hz'）
            
        Returns:
            音频数据（bytes）
        """
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_running_loop()
            # 如果在异步环境中，不应该使用同步接口
            raise RuntimeError(
                "在异步环境中，请使用 _text_to_speech_async 方法，而不是 text_to_speech"
            )
        except RuntimeError as e:
            if "异步环境" in str(e):
                raise
            # 如果没有运行中的事件循环，创建新的
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(
                self._text_to_speech_async(text, voice, rate, volume, pitch)
            )
    
    async def _list_voices_async(self, language: Optional[str] = None) -> List[Dict]:
        """
        异步列出可用的语音列表
        
        Args:
            language: 语言代码（如 'en', 'zh'），None 表示所有语言
            
        Returns:
            语音列表
        """
        voices = await edge_tts.list_voices()
        
        if language:
            # 过滤指定语言的语音
            filtered_voices = []
            for voice in voices:
                locale = voice.get('Locale', '')
                if locale.lower().startswith(language.lower()):
                    filtered_voices.append(voice)
            return filtered_voices
        
        return voices
    
    def list_voices(self, language: Optional[str] = None) -> List[Dict]:
        """
        列出可用的语音列表（同步接口）
        
        注意：在 FastAPI 异步环境中，应该直接使用 _list_voices_async
        
        Args:
            language: 语言代码（如 'en', 'zh'），None 表示所有语言
            
        Returns:
            语音列表
        """
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_running_loop()
            # 如果在异步环境中，不应该使用同步接口
            raise RuntimeError(
                "在异步环境中，请使用 _list_voices_async 方法，而不是 list_voices"
            )
        except RuntimeError as e:
            if "异步环境" in str(e):
                raise
            # 如果没有运行中的事件循环，创建新的
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(self._list_voices_async(language))


class OpenAITTSService(TTSService):
    """使用 OpenAI TTS API 的服务（通过 yunwu.ai 代理）"""
    
    # OpenAI TTS 支持的语音列表
    SUPPORTED_VOICES = [
        "alloy",   # 中性，平衡
        "echo",    # 男性，深沉
        "fable",   # 男性，英国口音
        "onyx",    # 男性，深沉
        "nova",    # 女性，年轻
        "shimmer", # 女性，温暖
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini-tts",  # yunwu.ai 使用的模型名
        default_voice: str = "alloy"
    ):
        """
        初始化 OpenAI TTS 服务
        
        Args:
            api_key: OpenAI API 密钥（默认使用全局配置）
            base_url: API base URL（默认使用 yunwu.ai）
            model: TTS 模型（tts-1 或 tts-1-hd）
            default_voice: 默认语音
        """
        # 使用全局配置
        api_key = api_key or llm_config.get_openai_api_key()
        base_url = base_url or llm_config.get_openai_base_url()
        
        if not api_key:
            raise ValueError("OpenAI API key is required")
        
        # 确保 base_url 格式正确
        if base_url and not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        
        # 创建httpx客户端（避免proxies参数问题）
        try:
            import httpx
            http_client = httpx.Client(
                timeout=60.0,
                follow_redirects=True
            )
            self.client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
        except Exception:
            # 如果创建自定义客户端失败，直接创建（可能在某些版本中工作）
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.default_voice = default_voice if default_voice in self.SUPPORTED_VOICES else "alloy"
    
    async def _text_to_speech_async(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> bytes:
        """
        异步将文本转换为语音音频
        
        Args:
            text: 要转换的文本
            voice: 语音名称（alloy, echo, fable, onyx, nova, shimmer）
            rate, volume, pitch: OpenAI TTS 不支持这些参数，会被忽略
            
        Returns:
            音频数据（bytes）
        """
        voice = voice or self.default_voice
        
        # 验证语音名称
        if voice not in self.SUPPORTED_VOICES:
            voice = self.default_voice
        
        try:
            # 调用 OpenAI TTS API
            response = self.client.audio.speech.create(
                model=self.model,
                voice=voice,
                input=text
            )
            
            # 读取音频数据
            audio_data = response.content
            
            return audio_data
            
        except Exception as e:
            raise Exception(f"OpenAI TTS 生成失败: {str(e)}")
    
    def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> bytes:
        """
        将文本转换为语音音频（同步接口）
        """
        try:
            loop = asyncio.get_running_loop()
            raise RuntimeError(
                "在异步环境中，请使用 _text_to_speech_async 方法"
            )
        except RuntimeError as e:
            if "异步环境" in str(e):
                raise
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self._text_to_speech_async(text, voice, rate, volume, pitch)
                )
            finally:
                loop.close()
    
    def list_voices(self, language: Optional[str] = None) -> List[Dict]:
        """
        列出可用的语音列表
        
        Args:
            language: 语言代码（OpenAI TTS 不支持按语言过滤）
            
        Returns:
            语音列表
        """
        voices = []
        for voice_name in self.SUPPORTED_VOICES:
            voices.append({
                "ShortName": voice_name,
                "Locale": "en-US",  # OpenAI TTS 主要支持英语
                "Gender": self._get_voice_gender(voice_name),
                "FriendlyName": f"OpenAI {voice_name.capitalize()}"
            })
        
        return voices
    
    def _get_voice_gender(self, voice: str) -> str:
        """获取语音的性别"""
        gender_map = {
            "alloy": "Neutral",
            "echo": "Male",
            "fable": "Male",
            "onyx": "Male",
            "nova": "Female",
            "shimmer": "Female",
        }
        return gender_map.get(voice, "Unknown")


class TTSServiceFactory:
    """TTS服务工厂"""
    
    @staticmethod
    def create(provider: str = "edge-tts", **kwargs) -> TTSService:
        """
        创建TTS服务实例
        
        Args:
            provider: TTS服务提供商
                - "edge-tts": Microsoft Edge TTS（免费，在线）
                - "openai": OpenAI TTS API（通过 yunwu.ai 代理）
                - "minimax": MiniMax TTS（高质量中文语音）
            **kwargs: 其他参数
                - edge-tts: default_voice, default_rate, default_volume, default_pitch
                - openai: api_key, base_url, model, default_voice
                - minimax: api_key, model, default_voice, speed
        """
        if provider == "edge-tts":
            return EdgeTTSService(**kwargs)
        elif provider == "openai":
            return OpenAITTSService(**kwargs)
        elif provider == "minimax":
            from services.minimax_tts import MiniMaxTTSService, MiniMaxTTSConfig
            config = MiniMaxTTSConfig(
                api_key=kwargs.get("api_key", ""),
                model=kwargs.get("model", "speech-2.6-hd"),
                default_voice=kwargs.get("default_voice", "male-qn-jingying"),
                speed=kwargs.get("speed", 1.0)
            )
            return MiniMaxTTSService(config)
        else:
            raise ValueError(
                f"Unsupported TTS provider: {provider}. "
                "Supported providers: 'edge-tts', 'openai', 'minimax'"
            )

