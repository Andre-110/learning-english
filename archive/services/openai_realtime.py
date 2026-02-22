"""
OpenAI Realtime API 服务 - 实现端到端语音对话

使用 OpenAI Realtime API 实现：
- 音频输入 → 音频输出（无需单独STT/TTS）
- 流式双向通信
- 超低延迟响应

参考文档: https://platform.openai.com/docs/guides/realtime
"""
import asyncio
import base64
import json
import websockets
from typing import Optional, Dict, Any, AsyncGenerator, Callable
from dataclasses import dataclass
from enum import Enum

from config.llm_config import llm_config
from services.utils.logger import get_logger

logger = get_logger("services.openai_realtime")


class RealtimeEventType(Enum):
    """Realtime API 事件类型"""
    # 客户端事件
    SESSION_UPDATE = "session.update"
    INPUT_AUDIO_BUFFER_APPEND = "input_audio_buffer.append"
    INPUT_AUDIO_BUFFER_COMMIT = "input_audio_buffer.commit"
    INPUT_AUDIO_BUFFER_CLEAR = "input_audio_buffer.clear"
    CONVERSATION_ITEM_CREATE = "conversation.item.create"
    RESPONSE_CREATE = "response.create"
    RESPONSE_CANCEL = "response.cancel"
    
    # 服务端事件
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    INPUT_AUDIO_BUFFER_COMMITTED = "input_audio_buffer.committed"
    INPUT_AUDIO_BUFFER_CLEARED = "input_audio_buffer.cleared"
    INPUT_AUDIO_BUFFER_SPEECH_STARTED = "input_audio_buffer.speech_started"
    INPUT_AUDIO_BUFFER_SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
    CONVERSATION_ITEM_CREATED = "conversation.item.created"
    RESPONSE_CREATED = "response.created"
    RESPONSE_DONE = "response.done"
    RESPONSE_OUTPUT_ITEM_ADDED = "response.output_item.added"
    RESPONSE_OUTPUT_ITEM_DONE = "response.output_item.done"
    RESPONSE_CONTENT_PART_ADDED = "response.content_part.added"
    RESPONSE_CONTENT_PART_DONE = "response.content_part.done"
    RESPONSE_TEXT_DELTA = "response.text.delta"
    RESPONSE_TEXT_DONE = "response.text.done"
    RESPONSE_AUDIO_DELTA = "response.audio.delta"
    RESPONSE_AUDIO_DONE = "response.audio.done"
    RESPONSE_AUDIO_TRANSCRIPT_DELTA = "response.audio_transcript.delta"
    RESPONSE_AUDIO_TRANSCRIPT_DONE = "response.audio_transcript.done"
    RATE_LIMITS_UPDATED = "rate_limits.updated"
    ERROR = "error"


@dataclass
class RealtimeConfig:
    """Realtime API 配置"""
    model: str = "gpt-4o-realtime-preview"
    voice: str = "alloy"  # alloy, echo, shimmer
    modalities: list = None  # ["text", "audio"]
    instructions: str = None
    input_audio_format: str = "pcm16"  # pcm16, g711_ulaw, g711_alaw
    output_audio_format: str = "pcm16"
    input_audio_transcription: dict = None  # {"model": "whisper-1"}
    turn_detection: dict = None  # VAD配置
    temperature: float = 0.8
    max_response_output_tokens: int = 4096
    
    def __post_init__(self):
        if self.modalities is None:
            self.modalities = ["text", "audio"]
        if self.input_audio_transcription is None:
            self.input_audio_transcription = {"model": "whisper-1"}
        if self.turn_detection is None:
            # 服务端VAD配置
            self.turn_detection = {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500
            }


class OpenAIRealtimeService:
    """OpenAI Realtime API 服务"""
    
    # OpenAI Realtime WebSocket URL
    REALTIME_URL = "wss://api.openai.com/v1/realtime"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[RealtimeConfig] = None
    ):
        """
        初始化 Realtime 服务
        
        Args:
            api_key: OpenAI API密钥
            config: Realtime配置
        """
        self.api_key = api_key or llm_config.get_openai_api_key()
        self.config = config or RealtimeConfig()
        
        # WebSocket连接
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        
        # 事件回调
        self.on_audio_delta: Optional[Callable[[bytes], None]] = None
        self.on_text_delta: Optional[Callable[[str], None]] = None
        self.on_transcript_delta: Optional[Callable[[str], None]] = None
        self.on_response_done: Optional[Callable[[Dict], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_speech_started: Optional[Callable[[], None]] = None
        self.on_speech_stopped: Optional[Callable[[], None]] = None
        
        logger.info(f"OpenAI Realtime服务初始化: model={self.config.model}, voice={self.config.voice}")
    
    async def connect(self) -> bool:
        """
        连接到 OpenAI Realtime API
        
        Returns:
            是否连接成功
        """
        try:
            # 构建WebSocket URL
            url = f"{self.REALTIME_URL}?model={self.config.model}"
            
            # 连接头
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            logger.info(f"正在连接 OpenAI Realtime API: {url}")
            
            self.ws = await websockets.connect(
                url,
                additional_headers=headers,
                ping_interval=30,
                ping_timeout=10
            )
            
            self.connected = True
            logger.info("OpenAI Realtime API 连接成功")
            
            # 等待 session.created 事件
            response = await self.ws.recv()
            event = json.loads(response)
            
            if event.get("type") == "session.created":
                logger.info(f"会话已创建: {event.get('session', {}).get('id')}")
                
                # 更新会话配置
                await self._update_session()
                
                return True
            else:
                logger.warning(f"意外的初始事件: {event.get('type')}")
                return True
                
        except Exception as e:
            logger.error(f"连接 Realtime API 失败: {e}", exc_info=True)
            self.connected = False
            return False
    
    async def _update_session(self):
        """更新会话配置"""
        session_config = {
            "type": "session.update",
            "session": {
                "modalities": self.config.modalities,
                "instructions": self.config.instructions or self._get_default_instructions(),
                "voice": self.config.voice,
                "input_audio_format": self.config.input_audio_format,
                "output_audio_format": self.config.output_audio_format,
                "input_audio_transcription": self.config.input_audio_transcription,
                "turn_detection": self.config.turn_detection,
                "temperature": self.config.temperature,
                "max_response_output_tokens": self.config.max_response_output_tokens
            }
        }
        
        await self.ws.send(json.dumps(session_config))
        logger.info("会话配置已更新")
    
    def _get_default_instructions(self) -> str:
        """获取默认指令"""
        return """You are LinguaCoach, a friendly and encouraging English language tutor.

Your role is to:
1. Help users practice their spoken English through natural conversation
2. Assess their English proficiency based on vocabulary, grammar, and fluency
3. Provide gentle corrections and suggestions when appropriate
4. Ask follow-up questions to keep the conversation engaging
5. Adjust your language complexity to match the user's level

Guidelines:
- Be patient and supportive
- Speak clearly and at an appropriate pace
- If the user makes mistakes, acknowledge what they said correctly first
- Give brief, encouraging feedback
- Keep responses concise (2-3 sentences) to maintain conversation flow

Remember: Focus on communication, not perfection. Celebrate progress!"""
    
    async def disconnect(self):
        """断开连接"""
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.connected = False
        logger.info("Realtime API 连接已断开")
    
    async def send_audio(self, audio_data: bytes):
        """
        发送音频数据
        
        Args:
            audio_data: PCM16格式的音频数据
        """
        if not self.connected or not self.ws:
            raise RuntimeError("未连接到 Realtime API")
        
        # Base64编码音频数据
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        event = {
            "type": "input_audio_buffer.append",
            "audio": audio_base64
        }
        
        await self.ws.send(json.dumps(event))
    
    async def commit_audio(self):
        """提交音频缓冲区，触发处理"""
        if not self.connected or not self.ws:
            raise RuntimeError("未连接到 Realtime API")
        
        event = {"type": "input_audio_buffer.commit"}
        await self.ws.send(json.dumps(event))
        logger.debug("音频缓冲区已提交")
    
    async def create_response(self):
        """创建响应（手动触发）"""
        if not self.connected or not self.ws:
            raise RuntimeError("未连接到 Realtime API")
        
        event = {"type": "response.create"}
        await self.ws.send(json.dumps(event))
        logger.debug("响应请求已发送")
    
    async def cancel_response(self):
        """取消当前响应"""
        if not self.connected or not self.ws:
            return
        
        event = {"type": "response.cancel"}
        await self.ws.send(json.dumps(event))
        logger.debug("响应已取消")
    
    async def send_text(self, text: str):
        """
        发送文本消息
        
        Args:
            text: 文本内容
        """
        if not self.connected or not self.ws:
            raise RuntimeError("未连接到 Realtime API")
        
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": text
                    }
                ]
            }
        }
        
        await self.ws.send(json.dumps(event))
        logger.debug(f"文本消息已发送: {text[:50]}...")
    
    async def listen(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        监听服务端事件
        
        Yields:
            事件字典
        """
        if not self.connected or not self.ws:
            raise RuntimeError("未连接到 Realtime API")
        
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type", "")
                
                # 处理不同类型的事件
                if event_type == "response.audio.delta":
                    # 音频增量
                    audio_base64 = event.get("delta", "")
                    if audio_base64 and self.on_audio_delta:
                        audio_data = base64.b64decode(audio_base64)
                        self.on_audio_delta(audio_data)
                
                elif event_type == "response.text.delta":
                    # 文本增量
                    text = event.get("delta", "")
                    if text and self.on_text_delta:
                        self.on_text_delta(text)
                
                elif event_type == "response.audio_transcript.delta":
                    # 音频转录增量
                    transcript = event.get("delta", "")
                    if transcript and self.on_transcript_delta:
                        self.on_transcript_delta(transcript)
                
                elif event_type == "response.done":
                    # 响应完成
                    if self.on_response_done:
                        self.on_response_done(event.get("response", {}))
                
                elif event_type == "input_audio_buffer.speech_started":
                    # 检测到语音开始
                    if self.on_speech_started:
                        self.on_speech_started()
                
                elif event_type == "input_audio_buffer.speech_stopped":
                    # 检测到语音结束
                    if self.on_speech_stopped:
                        self.on_speech_stopped()
                
                elif event_type == "error":
                    # 错误
                    error_msg = event.get("error", {}).get("message", "Unknown error")
                    logger.error(f"Realtime API 错误: {error_msg}")
                    if self.on_error:
                        self.on_error(error_msg)
                
                yield event
                
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WebSocket连接关闭: {e}")
            self.connected = False
        except Exception as e:
            logger.error(f"监听事件错误: {e}", exc_info=True)
            raise


class RealtimeConversationManager:
    """Realtime 对话管理器 - 封装完整的对话流程"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        instructions: Optional[str] = None,
        voice: str = "alloy"
    ):
        """
        初始化对话管理器
        
        Args:
            api_key: OpenAI API密钥
            instructions: 系统指令
            voice: 语音类型
        """
        config = RealtimeConfig(
            voice=voice,
            instructions=instructions
        )
        self.service = OpenAIRealtimeService(api_key=api_key, config=config)
        
        # 对话状态
        self.is_speaking = False
        self.current_response_text = ""
        self.current_response_audio = bytearray()
        self.user_transcript = ""
    
    async def start(self) -> bool:
        """启动对话"""
        return await self.service.connect()
    
    async def stop(self):
        """停止对话"""
        await self.service.disconnect()
    
    async def process_audio_chunk(self, audio_chunk: bytes):
        """
        处理音频块
        
        Args:
            audio_chunk: PCM16格式的音频数据
        """
        await self.service.send_audio(audio_chunk)
    
    async def end_turn(self):
        """结束用户发言，触发AI响应"""
        await self.service.commit_audio()
        await self.service.create_response()
    
    def set_callbacks(
        self,
        on_audio: Optional[Callable[[bytes], None]] = None,
        on_text: Optional[Callable[[str], None]] = None,
        on_user_transcript: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[Dict], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """设置回调函数"""
        self.service.on_audio_delta = on_audio
        self.service.on_text_delta = on_text
        self.service.on_transcript_delta = on_user_transcript
        self.service.on_response_done = on_done
        self.service.on_error = on_error
    
    async def listen_events(self) -> AsyncGenerator[Dict[str, Any], None]:
        """监听所有事件"""
        async for event in self.service.listen():
            yield event


# 工厂函数
def create_realtime_service(
    api_key: Optional[str] = None,
    voice: str = "alloy",
    instructions: Optional[str] = None
) -> OpenAIRealtimeService:
    """创建 Realtime 服务实例"""
    config = RealtimeConfig(voice=voice, instructions=instructions)
    return OpenAIRealtimeService(api_key=api_key, config=config)


def create_realtime_conversation(
    api_key: Optional[str] = None,
    voice: str = "alloy",
    instructions: Optional[str] = None
) -> RealtimeConversationManager:
    """创建 Realtime 对话管理器"""
    return RealtimeConversationManager(
        api_key=api_key,
        voice=voice,
        instructions=instructions
    )

