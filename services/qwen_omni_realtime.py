"""
Qwen3-Omni Realtime API 服务封装

使用 DashScope WebSocket Realtime API 实现实时语音对话
支持：
- 实时语音输入/输出
- 服务端 VAD（自动检测说话开始/结束）
- 打断支持（用户说话时停止 AI 播放）
- 独立转录模型
"""
import os
import base64
import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

try:
    from dashscope.audio.qwen_omni import (
        OmniRealtimeConversation,
        OmniRealtimeCallback,
        MultiModality,
        AudioFormat
    )
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    OmniRealtimeConversation = None
    OmniRealtimeCallback = object
    MultiModality = None
    AudioFormat = None

import dashscope
from config.settings import Settings
settings = Settings()

logger = logging.getLogger(__name__)


class RealtimeEventType(str, Enum):
    """Realtime 事件类型"""
    SESSION_CREATED = "session.created"
    TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"
    AUDIO_TRANSCRIPT_DELTA = "response.audio_transcript.delta"
    AUDIO_DELTA = "response.audio.delta"
    SPEECH_STARTED = "input_audio_buffer.speech_started"
    SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
    RESPONSE_DONE = "response.done"
    ERROR = "error"


@dataclass
class RealtimeConfig:
    """Realtime 配置"""
    model: str = "qwen3-omni-flash-realtime"
    voice: str = "Cherry"
    input_audio_format: str = "pcm_16000hz_mono_16bit"
    output_audio_format: str = "pcm_24000hz_mono_16bit"
    enable_transcription: bool = True
    transcription_model: str = "gummy-realtime-v1"
    enable_vad: bool = True
    vad_type: str = "server_vad"
    # WebSocket URL - 北京地域
    ws_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"


class RealtimeCallbackHandler(OmniRealtimeCallback if DASHSCOPE_AVAILABLE else object):
    """
    Realtime 回调处理器
    
    将 DashScope 的回调事件转发到异步队列，供 WebSocket 端点消费
    """
    
    def __init__(self, event_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.event_queue = event_queue
        self.loop = loop
        self.session_id: Optional[str] = None
        
    def _put_event(self, event_type: str, data: Dict[str, Any]):
        """线程安全地将事件放入异步队列"""
        asyncio.run_coroutine_threadsafe(
            self.event_queue.put({"type": event_type, "data": data}),
            self.loop
        )
    
    def on_open(self) -> None:
        """连接打开"""
        logger.info("[Realtime] 连接已打开")
        self._put_event("connected", {})
    
    def on_close(self, close_status_code, close_msg) -> None:
        """连接关闭"""
        logger.info(f"[Realtime] 连接关闭: code={close_status_code}, msg={close_msg}")
        self._put_event("disconnected", {
            "code": close_status_code,
            "message": close_msg
        })
    
    def on_event(self, response: dict) -> None:
        """处理 Realtime 事件"""
        try:
            event_type = response.get('type', '')
            
            if event_type == RealtimeEventType.SESSION_CREATED:
                self.session_id = response.get('session', {}).get('id')
                logger.info(f"[Realtime] 会话创建: {self.session_id}")
                self._put_event("session_created", {"session_id": self.session_id})
            
            elif event_type == RealtimeEventType.TRANSCRIPTION_COMPLETED:
                transcript = response.get('transcript', '')
                logger.info(f"[Realtime] 转录完成: {transcript[:50]}...")
                self._put_event("transcription", {"text": transcript})
            
            elif event_type == RealtimeEventType.AUDIO_TRANSCRIPT_DELTA:
                delta = response.get('delta', '')
                self._put_event("text_delta", {"delta": delta})
            
            elif event_type == RealtimeEventType.AUDIO_DELTA:
                audio_b64 = response.get('delta', '')
                self._put_event("audio_delta", {"audio": audio_b64})
            
            elif event_type == RealtimeEventType.SPEECH_STARTED:
                logger.info("[Realtime] VAD: 检测到说话开始")
                self._put_event("speech_started", {})
            
            elif event_type == RealtimeEventType.SPEECH_STOPPED:
                logger.info("[Realtime] VAD: 检测到说话结束")
                self._put_event("speech_stopped", {})
            
            elif event_type == RealtimeEventType.RESPONSE_DONE:
                logger.info("[Realtime] 响应完成")
                self._put_event("response_done", {})
            
            elif event_type == RealtimeEventType.ERROR:
                error_msg = response.get('error', {}).get('message', 'Unknown error')
                logger.error(f"[Realtime] 错误: {error_msg}")
                self._put_event("error", {"message": error_msg})
            
        except Exception as e:
            logger.error(f"[Realtime] 事件处理错误: {e}")
            self._put_event("error", {"message": str(e)})


class QwenOmniRealtimeService:
    """
    Qwen-Omni Realtime 服务
    
    封装 DashScope Realtime API，提供异步接口
    """
    
    def __init__(self, config: Optional[RealtimeConfig] = None):
        if not DASHSCOPE_AVAILABLE:
            raise ImportError("dashscope SDK 未安装或版本过低，需要 >= 1.23.9")
        
        self.config = config or RealtimeConfig()
        self.conversation: Optional[OmniRealtimeConversation] = None
        self.callback_handler: Optional[RealtimeCallbackHandler] = None
        self.event_queue: Optional[asyncio.Queue] = None
        self.is_connected = False
        
        # 设置 API Key
        dashscope.api_key = settings.dashscope_api_key
        
    async def connect(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        """
        建立 Realtime 连接
        
        Returns:
            事件队列，用于接收 Realtime 事件
        """
        if self.is_connected:
            logger.warning("[Realtime] 已经连接，跳过")
            return self.event_queue
        
        # 创建事件队列
        self.event_queue = asyncio.Queue()
        
        # 创建回调处理器
        self.callback_handler = RealtimeCallbackHandler(self.event_queue, loop)
        
        # 创建 Realtime 会话
        self.conversation = OmniRealtimeConversation(
            model=self.config.model,
            callback=self.callback_handler,
            url=self.config.ws_url
        )
        
        # 在线程中建立连接（DashScope SDK 是同步的）
        logger.info("[Realtime] 正在建立 WebSocket 连接...")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self.conversation.connect),
                timeout=30  # 30秒超时
            )
            logger.info("[Realtime] WebSocket 连接已建立")
        except asyncio.TimeoutError:
            logger.error("[Realtime] 连接超时（30秒）")
            raise Exception("Realtime 连接超时")
        except Exception as e:
            logger.error(f"[Realtime] 连接失败: {e}")
            raise
        
        # 配置会话
        audio_format_map = {
            "pcm_16000hz_mono_16bit": AudioFormat.PCM_16000HZ_MONO_16BIT,
            "pcm_24000hz_mono_16bit": AudioFormat.PCM_24000HZ_MONO_16BIT,
        }
        
        input_format = audio_format_map.get(
            self.config.input_audio_format, 
            AudioFormat.PCM_16000HZ_MONO_16BIT
        )
        output_format = audio_format_map.get(
            self.config.output_audio_format,
            AudioFormat.PCM_24000HZ_MONO_16BIT
        )
        
        # 配置会话参数
        logger.info(f"[Realtime] 正在配置会话: voice={self.config.voice}")
        def configure_session():
            self.conversation.update_session(
                [MultiModality.AUDIO, MultiModality.TEXT],  # output_modalities 作为位置参数
                voice=self.config.voice,
                input_audio_format=input_format,
                output_audio_format=output_format,
                enable_input_audio_transcription=self.config.enable_transcription,
                input_audio_transcription_model=self.config.transcription_model,
                enable_turn_detection=self.config.enable_vad,
                turn_detection_type=self.config.vad_type,
            )
        
        try:
            await loop.run_in_executor(None, configure_session)
            logger.info("[Realtime] 会话配置成功")
        except Exception as e:
            logger.error(f"[Realtime] 会话配置失败: {e}")
            raise
        
        self.is_connected = True
        logger.info("[Realtime] 连接成功，会话已配置")
        
        return self.event_queue
    
    async def send_audio(self, audio_data: bytes, loop: asyncio.AbstractEventLoop):
        """
        发送音频数据
        
        Args:
            audio_data: PCM 音频数据 (16kHz, mono, 16bit)
            loop: 事件循环
        """
        if not self.is_connected or not self.conversation:
            logger.warning("[Realtime] 未连接，无法发送音频")
            return
        
        audio_b64 = base64.b64encode(audio_data).decode('ascii')
        await loop.run_in_executor(
            None,
            lambda: self.conversation.append_audio(audio_b64)
        )
    
    async def send_system_prompt(self, prompt: str, loop: asyncio.AbstractEventLoop):
        """
        发送系统提示词
        
        注意：Qwen-Omni Realtime API 在 Server VAD 模式下，instructions 需要通过
        create_response 传递。但 Server VAD 会自动触发 create_response，
        所以这里只是记录 prompt，实际效果可能有限。
        
        Args:
            prompt: 系统提示词
            loop: 事件循环
        """
        if not self.is_connected or not self.conversation:
            logger.warning("[Realtime] 未连接，无法发送系统提示词")
            return
        
        # Qwen-Omni Realtime 的 Server VAD 模式不支持预设 instructions
        # 这里只是记录日志，实际对话由模型默认行为控制
        logger.info(f"[Realtime] 系统提示词（注意：Server VAD 模式下可能不生效）: {prompt[:100]}...")
    
    async def trigger_initial_greeting(self, greeting_instruction: str, loop: asyncio.AbstractEventLoop):
        """
        触发 AI 的初始问候
        
        通过 create_response 让 AI 主动说话
        
        Args:
            greeting_instruction: 问候指令，如 "Say hello and ask the user what they want to practice today"
            loop: 事件循环
        """
        if not self.is_connected or not self.conversation:
            logger.warning("[Realtime] 未连接，无法触发初始问候")
            return
        
        try:
            def create_greeting():
                self.conversation.create_response(
                    instructions=greeting_instruction,
                    output_modalities=[MultiModality.AUDIO, MultiModality.TEXT]
                )
            
            await loop.run_in_executor(None, create_greeting)
            logger.info(f"[Realtime] 已触发初始问候: {greeting_instruction[:50]}...")
        except Exception as e:
            logger.error(f"[Realtime] 触发初始问候失败: {e}")
    
    async def interrupt(self, loop: asyncio.AbstractEventLoop):
        """
        打断当前响应
        """
        if not self.is_connected or not self.conversation:
            return
        
        # 清空输入缓冲区
        await loop.run_in_executor(
            None,
            lambda: self.conversation.clear_audio()
        )
        logger.info("[Realtime] 已打断响应")
    
    async def disconnect(self, loop: asyncio.AbstractEventLoop):
        """
        断开连接
        """
        if not self.is_connected or not self.conversation:
            return
        
        await loop.run_in_executor(None, self.conversation.close)
        self.is_connected = False
        self.conversation = None
        self.callback_handler = None
        logger.info("[Realtime] 已断开连接")


# 工厂函数
def create_realtime_service(config: Optional[RealtimeConfig] = None) -> QwenOmniRealtimeService:
    """创建 Realtime 服务实例"""
    return QwenOmniRealtimeService(config)

