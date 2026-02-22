"""
豆包 Bigmodel 流式 ASR 服务

使用字节跳动豆包大模型 ASR 进行实时语音转文字。
API: wss://openspeech.bytedance.com/api/v3/sauc/bigmodel

优势：
- 中文优化：对中文识别效果更好
- 低延迟：流式识别，边说边转
- 大模型能力：理解上下文，更准确

协议说明：
- 使用二进制协议 + Gzip 压缩
- 参考 UserGenie.ai 项目的 doubao-protocol.ts
"""
import asyncio
import gzip
import json
import struct
import hashlib
import hmac
import time
import uuid
from typing import Optional, Callable, Any, BinaryIO
from dataclasses import dataclass, field

import websockets

from services.speech import SpeechService
from services.utils.logger import get_logger

logger = get_logger("services.doubao_asr")


@dataclass
class DoubaoASRConfig:
    """豆包 ASR 配置"""
    
    # API 配置（从环境变量获取）
    app_key: str = ""
    access_key: str = ""
    secret_key: str = ""  # 新增
    
    # 端点（使用 async 版本）
    endpoint: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    
    # 音频配置
    sample_rate: int = 16000
    channels: int = 1
    bits: int = 16
    audio_format: str = "pcm"
    
    # 识别配置
    language: str = "en"  # 英语学习场景默认英语
    
    # 超时配置
    connection_timeout: float = 10.0
    read_timeout: float = 30.0
    
    def __post_init__(self):
        import os
        if not self.app_key:
            self.app_key = os.getenv("DOUBAO_ASR_APP_KEY", "")
        if not self.access_key:
            self.access_key = os.getenv("DOUBAO_ASR_ACCESS_KEY", "")
        if not self.secret_key:
            self.secret_key = os.getenv("DOUBAO_ASR_SECRET_KEY", "")
        if not self.endpoint:
            self.endpoint = os.getenv("DOUBAO_ASR_ENDPOINT", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async")


class DoubaoProtocol:
    """
    豆包 ASR 二进制协议处理
    
    协议格式：
    - Header: 4 bytes
    - Event ID: 4 bytes (可选)
    - Payload Size: 4 bytes
    - Payload: Gzip 压缩的 JSON/音频数据
    """
    
    # 协议常量
    PROTOCOL_VERSION = 0b0001
    
    # 消息类型
    MSG_TYPE_FULL_CLIENT_REQUEST = 0b0001
    MSG_TYPE_AUDIO_ONLY_REQUEST = 0b0010
    MSG_TYPE_SERVER_FULL_RESPONSE = 0b1001
    MSG_TYPE_SERVER_ERROR_RESPONSE = 0b1111
    
    # 消息类型标志
    FLAG_NO_SEQUENCE = 0b0000
    FLAG_MSG_WITH_EVENT = 0b0100
    
    # 序列化方法
    SERIAL_NONE = 0b0000
    SERIAL_JSON = 0b0001
    
    # 压缩类型
    COMPRESS_GZIP = 0b0001
    
    # 事件 ID
    EVENT_START_CONNECTION = 1
    EVENT_START_SESSION = 100
    EVENT_AUDIO_DATA = 200
    EVENT_FINISH = 300
    
    @classmethod
    def generate_header(
        cls,
        msg_type: int = None,
        msg_type_flags: int = None,
        serial_method: int = None,
        compress_type: int = None
    ) -> bytes:
        """生成协议头"""
        msg_type = msg_type if msg_type is not None else cls.MSG_TYPE_FULL_CLIENT_REQUEST
        msg_type_flags = msg_type_flags if msg_type_flags is not None else cls.FLAG_MSG_WITH_EVENT
        serial_method = serial_method if serial_method is not None else cls.SERIAL_JSON
        compress_type = compress_type if compress_type is not None else cls.COMPRESS_GZIP
        
        header = bytearray(4)
        header[0] = (cls.PROTOCOL_VERSION << 4) | 0b0001  # version + header size
        header[1] = (msg_type << 4) | msg_type_flags
        header[2] = (serial_method << 4) | compress_type
        header[3] = 0x00
        
        return bytes(header)
    
    @classmethod
    def create_full_request(cls, event_id: int, payload: dict) -> bytes:
        """创建完整请求（带事件 ID 和 JSON payload）"""
        header = cls.generate_header()
        event_bytes = struct.pack(">I", event_id)
        payload_bytes = gzip.compress(json.dumps(payload).encode('utf-8'))
        payload_size = struct.pack(">I", len(payload_bytes))
        
        return header + event_bytes + payload_size + payload_bytes
    
    @classmethod
    def create_audio_request(cls, event_id: int, audio_data: bytes) -> bytes:
        """创建音频请求"""
        header = cls.generate_header(
            msg_type=cls.MSG_TYPE_AUDIO_ONLY_REQUEST,
            serial_method=cls.SERIAL_NONE
        )
        event_bytes = struct.pack(">I", event_id)
        compressed_audio = gzip.compress(audio_data)
        payload_size = struct.pack(">I", len(compressed_audio))
        
        return header + event_bytes + payload_size + compressed_audio
    
    # Sequence flags (服务端响应使用)
    FLAG_NO_SEQUENCE = 0b0000
    FLAG_POS_SEQUENCE = 0b0001
    FLAG_NEG_SEQUENCE = 0b0011
    
    @classmethod
    def parse_response(cls, data: bytes) -> dict:
        """解析服务端响应"""
        if len(data) < 4:
            return {"error": "Response too short"}
        
        result = {}
        
        # 解析 header (4 bytes)
        header_size = data[0] & 0x0f  # 通常是 1，表示 4 bytes
        msg_type = data[1] >> 4
        msg_type_flags = data[1] & 0x0f
        serial_method = data[2] >> 4
        compress_type = data[2] & 0x0f
        
        result["msg_type"] = msg_type
        
        # 跳过 header (header_size * 4 bytes)
        offset = header_size * 4
        
        if msg_type == cls.MSG_TYPE_SERVER_FULL_RESPONSE:
            # 检查是否有 sequence（flags=0b0001 或 0b0011 表示有 sequence）
            if msg_type_flags in [cls.FLAG_POS_SEQUENCE, cls.FLAG_NEG_SEQUENCE]:
                if len(data) >= offset + 4:
                    result["sequence"] = struct.unpack(">i", data[offset:offset+4])[0]
                    offset += 4
            
            # 解析 payload size
            if len(data) >= offset + 4:
                payload_size = struct.unpack(">I", data[offset:offset+4])[0]
                offset += 4
                
                if len(data) >= offset + payload_size:
                    payload_data = data[offset:offset+payload_size]
                    
                    # 解压（compress_type=1 表示 GZIP）
                    if compress_type == cls.COMPRESS_GZIP:
                        try:
                            payload_data = gzip.decompress(payload_data)
                        except Exception as e:
                            logger.debug(f"[Doubao] GZIP 解压失败: {e}")

                    # 解析 JSON（serial_method=1 表示 JSON）
                    if serial_method == cls.SERIAL_JSON:
                        try:
                            result["payload"] = json.loads(payload_data.decode('utf-8'))
                        except Exception as e:
                            logger.debug(f"[Doubao] JSON 解析失败: {e}")
                            result["payload_raw"] = payload_data
                    else:
                        result["payload_raw"] = payload_data
        
        elif msg_type == cls.MSG_TYPE_SERVER_ERROR_RESPONSE:
            # 错误响应格式：error_code (4 bytes) + payload_size (4 bytes) + payload
            if len(data) >= offset + 4:
                result["error_code"] = struct.unpack(">I", data[offset:offset+4])[0]
                offset += 4
            
            if len(data) >= offset + 4:
                payload_size = struct.unpack(">I", data[offset:offset+4])[0]
                offset += 4
                
                if len(data) >= offset + payload_size:
                    payload_data = data[offset:offset+payload_size]
                    if compress_type == cls.COMPRESS_GZIP:
                        try:
                            payload_data = gzip.decompress(payload_data)
                        except Exception as e:
                            logger.debug(f"[Doubao] 错误响应 GZIP 解压失败: {e}")
                    result["error_msg"] = payload_data.decode('utf-8', errors='ignore')
        
        return result


class DoubaoASR:
    """
    豆包流式 ASR 服务
    
    使用示例：
    ```python
    asr = DoubaoASR()
    
    async def on_transcript(text, is_final):
        print(f"{'[Final]' if is_final else '[Interim]'} {text}")
    
    await asr.start_stream(on_transcript=on_transcript)
    
    while recording:
        await asr.send_audio(audio_chunk)
    
    result = await asr.stop_stream()
    ```
    """
    
    def __init__(self, config: Optional[DoubaoASRConfig] = None):
        self.config = config or DoubaoASRConfig()
        
        if not self.config.app_key or not self.config.access_key:
            raise ValueError(
                "豆包 ASR 配置缺失，请设置环境变量：\n"
                "  DOUBAO_ASR_APP_KEY=your_app_key\n"
                "  DOUBAO_ASR_ACCESS_KEY=your_access_key"
            )
        
        # WebSocket 连接
        self._ws = None
        self._is_connected = False
        
        # 序列号（与 UserGenie.ai 一致）
        self._seq = 1
        
        # 回调函数
        self._on_transcript: Optional[Callable] = None
        self._on_utterance_end: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        self._on_reconnect: Optional[Callable] = None  # 🆕 重连回调
        
        # 累积转录结果
        self._full_transcript = ""
        
        # 🆕 ASR 状态：最后一个结果是否为 final
        self._last_is_final = True  # 默认 True（空闲状态）
        
        # 🆕 utterance_end 防抖（避免反复识别问题）
        self._utterance_end_debounce_task: Optional[asyncio.Task] = None
        self._utterance_end_debounce_ms = 500  # 500ms 防抖延迟
        self._last_utterance_end_text = ""  # 上次触发 utterance_end 的文本
        
        # 接收任务
        self._receive_task = None
        
        # 🆕 自动重连配置（学习自 Deepgram ASR）
        self._auto_reconnect = True  # 是否启用自动重连
        self._max_reconnect_attempts = 3  # 最大重连次数
        self._reconnect_delay = 1.0  # 重连延迟（秒，递增）
        self._reconnect_attempts = 0  # 当前重连次数
        self._is_manual_close = False  # 是否手动关闭（不需要重连）
        
        # 🆕 音频缓冲（重连期间保存音频）
        self._pending_audio_buffer = []  # 缓冲的音频帧
        # 从配置读取缓冲大小（阶段 3 改进）
        try:
            from config.constants import ASR_AUDIO_BUFFER_SIZE
            self._max_buffer_size = ASR_AUDIO_BUFFER_SIZE
        except ImportError:
            self._max_buffer_size = 300  # 默认约 10 秒音频
        
        # 🆕 重连时保存的转录（参考 UserGenie.ai）
        self._preserved_transcript_before_reconnect = ""
        
        logger.info(f"DoubaoASR 初始化完成: language={self.config.language}")
    
    def _build_ws_url(self) -> str:
        """构建 WebSocket URL（带签名）"""
        # 简单 URL，认证通过 header 或 payload 传递
        return self.config.endpoint
    
    async def start_stream(
        self,
        on_transcript: Optional[Callable[[str, bool], Any]] = None,
        on_utterance_end: Optional[Callable[[], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_reconnect: Optional[Callable[[int, bool], Any]] = None  # 🆕 重连回调 (attempt, success)
    ) -> bool:
        """
        开始流式 ASR 连接
        
        Args:
            on_transcript: 转录回调 (text, is_final)
            on_utterance_end: 用户说完回调
            on_error: 错误回调
            on_reconnect: 🆕 重连回调 (attempt_count, is_success)
        
        Returns:
            是否成功连接
        """
        if self._is_connected:
            logger.warning("已有活跃连接，先关闭")
            await self.stop_stream()
        
        self._on_transcript = on_transcript
        self._on_utterance_end = on_utterance_end
        self._on_error = on_error
        self._on_reconnect = on_reconnect
        self._full_transcript = ""
        self._last_is_final = False  # 🆕 开始处理时设为 False（处理中）
        self._is_manual_close = False  # 🆕 重置手动关闭标志
        self._reconnect_attempts = 0  # 🆕 重置重连次数
        
        try:
            # 连接 WebSocket（使用 HTTP Headers 认证）
            url = self._build_ws_url()
            req_id = str(uuid.uuid4())
            
            # 构建认证 Headers（参考 UserGenie.ai）
            headers = {
                'X-Api-Resource-Id': 'volc.bigasr.sauc.duration',
                'X-Api-Request-Id': req_id,
                'X-Api-Access-Key': self.config.access_key,
                'X-Api-App-Key': self.config.app_key,
            }
            
            logger.info(f"[Doubao ASR] 连接: {url}")
            logger.info(f"[Doubao ASR] Auth: App-Key={self.config.app_key}, Access-Key={self.config.access_key[:8]}...")
            
            self._ws = await asyncio.wait_for(
                websockets.connect(url, extra_headers=headers),
                timeout=self.config.connection_timeout
            )
            
            # 发送初始化请求
            await self._send_start_request()
            
            # 启动接收任务
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            self._is_connected = True
            logger.info("[Doubao ASR] 流式连接已建立")
            return True
            
        except Exception as e:
            logger.error(f"[Doubao ASR] 连接失败: {e}")
            if self._on_error:
                await self._safe_callback(self._on_error, e)
            return False
    
    async def _send_start_request(self):
        """发送开始请求（参考 UserGenie.ai 实现）"""
        # 构建配置 - 使用 PCM 格式进行流式识别
        config_payload = {
            "user": {
                "uid": "linguacoach_user"
            },
            "audio": {
                "format": "pcm",  # 流式模式使用 PCM
                "codec": "raw",
                "rate": self.config.sample_rate,
                "bits": self.config.bits,
                "channel": self.config.channels
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": True,
                "enable_nonstream": False,
                "result_type": "full",  # 🔧 请求完整结果（包含文本）
                "show_text": True,       # 🔧 显示转录文本
                "language": self.config.language  # 🔧 指定语言
            }
        }
        
        # 使用序列号协议（与 UserGenie.ai 一致）
        self._seq = 1
        request = self._build_config_request(self._seq, config_payload)
        self._seq += 1
        
        await self._ws.send(request)
        logger.info("[Doubao ASR] 已发送配置请求")
    
    def _build_config_request(self, seq: int, payload: dict) -> bytes:
        """构建配置请求（与 UserGenie.ai 完全一致）"""
        import struct
        
        # Header: 4 bytes
        header = bytearray(4)
        header[0] = (0b0001 << 4) | 1  # version=1, header_size=1 (4 bytes)
        header[1] = (0b0001 << 4) | 0b0001  # msg_type=FULL_CLIENT_REQUEST, flags=POS_SEQUENCE
        header[2] = (0b0001 << 4) | 0b0001  # serialization=JSON, compression=GZIP
        header[3] = 0x00  # reserved
        
        # Payload
        payload_bytes = json.dumps(payload).encode('utf-8')
        compressed_payload = gzip.compress(payload_bytes)
        
        # Sequence: 4 bytes (big-endian signed int)
        seq_buffer = struct.pack(">i", seq)
        
        # Payload size: 4 bytes (big-endian unsigned int)
        size_buffer = struct.pack(">I", len(compressed_payload))
        
        return bytes(header) + seq_buffer + size_buffer + compressed_payload
    
    def _build_audio_request(self, seq: int, audio_data: bytes, is_last: bool = False) -> bytes:
        """构建音频请求（与 UserGenie.ai 完全一致）"""
        import struct
        
        # Header: 4 bytes
        header = bytearray(4)
        header[0] = (0b0001 << 4) | 1  # version=1, header_size=1
        
        if is_last:
            # 最后一个包：NEG_WITH_SEQUENCE (0b0011), seq 变为负数
            header[1] = (0b0010 << 4) | 0b0011  # msg_type=AUDIO_ONLY, flags=NEG_WITH_SEQUENCE
            seq = -seq
        else:
            header[1] = (0b0010 << 4) | 0b0001  # msg_type=AUDIO_ONLY, flags=POS_SEQUENCE
        
        # 🔧 修复：音频数据使用 serialization=NONE (0b0000)，不是 JSON (0b0001)
        header[2] = (0b0000 << 4) | 0b0001  # serialization=NONE, compression=GZIP
        header[3] = 0x00
        
        # 压缩音频数据
        compressed_audio = gzip.compress(audio_data)
        
        # Sequence
        seq_buffer = struct.pack(">i", seq)
        
        # Size
        size_buffer = struct.pack(">I", len(compressed_audio))
        
        return bytes(header) + seq_buffer + size_buffer + compressed_audio
    
    def _calculate_audio_energy(self, audio_data: bytes) -> float:
        """🆕 计算音频能量（RMS），用于判断是否静音"""
        if len(audio_data) < 2:
            return 0.0
        try:
            import struct
            # 假设 16-bit PCM
            samples = struct.unpack(f"<{len(audio_data)//2}h", audio_data)
            if not samples:
                return 0.0
            rms = (sum(s*s for s in samples) / len(samples)) ** 0.5
            return rms
        except Exception:
            return 0.0
    
    async def send_audio(self, audio_data: bytes, is_last: bool = False) -> bool:
        """
        发送音频数据
        
        🆕 支持音频缓冲：未连接时缓存音频，重连后自动发送
        """
        if not self._is_connected or not self._ws:
            # 🆕 未连接时缓冲音频（用于重连后发送）
            if len(self._pending_audio_buffer) < self._max_buffer_size:
                self._pending_audio_buffer.append(audio_data)
                if len(self._pending_audio_buffer) % 20 == 1:
                    logger.info(f"[Doubao ASR] 未连接，缓冲音频 #{len(self._pending_audio_buffer)}")
            else:
                # 缓冲满，丢弃最老的
                self._pending_audio_buffer.pop(0)
                self._pending_audio_buffer.append(audio_data)
            return False
        
        try:
            request = self._build_audio_request(self._seq, audio_data, is_last)
            if not is_last:
                self._seq += 1
            await self._ws.send(request)
            return True
        except websockets.exceptions.ConnectionClosed as e:
            # 🔧 连接已关闭（服务端超时等），缓冲音频
            logger.warning(f"[Doubao ASR] 发送时连接已关闭: {e}")
            self._is_connected = False
            if len(self._pending_audio_buffer) < self._max_buffer_size:
                self._pending_audio_buffer.append(audio_data)
            return False
        except Exception as e:
            logger.error(f"[Doubao ASR] 发送音频失败: {e}")
            self._is_connected = False  # 🔧 发送失败也标记连接不可用
            if len(self._pending_audio_buffer) < self._max_buffer_size:
                self._pending_audio_buffer.append(audio_data)
            return False
    
    async def stop_stream(self) -> str:
        """停止流式连接"""
        # 🔧 修复：防止重复调用（stop_audio 和 finally 各调用一次会导致状态异常）
        if self._is_manual_close and not self._is_connected and not self._ws:
            logger.debug("[Doubao ASR] stop_stream 已调用过，跳过重复调用")
            return self._full_transcript

        self._is_manual_close = True  # 标记为手动关闭（不触发重连）
        
        # 🆕 取消防抖任务
        if self._utterance_end_debounce_task and not self._utterance_end_debounce_task.done():
            self._utterance_end_debounce_task.cancel()
            try:
                await self._utterance_end_debounce_task
            except asyncio.CancelledError:
                pass
        
        # 发送结束请求（使用序列号协议，与 start/audio 一致）
        if self._ws and self._is_connected:
            try:
                # 🔧 修复：发送最后一个空音频包（is_last=True）来触发结束
                # 这样服务端会返回最终结果
                finish_request = self._build_audio_request(self._seq, b'', is_last=True)
                await self._ws.send(finish_request)

                # 等待服务端返回最终结果（固定等待；更稳妥做法是等收到 is_final 再关）
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"[Doubao ASR] 发送结束请求失败: {e}")
        
        # 取消接收任务
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        # 关闭连接
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug(f"[Doubao ASR] 关闭连接失败: {e}")

        self._is_connected = False
        self._ws = None
        self._pending_audio_buffer = []  # 🆕 清空音频缓冲
        
        result = self._full_transcript
        logger.info(f"[Doubao ASR] 流式连接已关闭，完整转录: {result[:50]}...")
        
        return result
    
    async def _receive_loop(self):
        """接收服务端消息的循环"""
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    await self._handle_response(message)
        except websockets.exceptions.ConnectionClosed as e:
            # 🆕 提取关闭代码和原因
            close_code = e.code if hasattr(e, 'code') else 1006
            close_reason = e.reason if hasattr(e, 'reason') else str(e)
            self._is_connected = False
            # 🆕 自动重连逻辑（带详细日志）
            await self._handle_connection_closed(close_code, close_reason)
        except asyncio.CancelledError:
            self._is_connected = False  # 取消时不重连
        except Exception as e:
            logger.error(f"[Doubao ASR] 接收错误: {e}")
            self._is_connected = False
            if self._on_error:
                await self._safe_callback(self._on_error, e)
            # 🆕 自动重连逻辑
            await self._handle_connection_closed()
    
    async def _handle_connection_closed(self, close_code: int = 1006, close_reason: str = "unknown"):
        """🆕 处理连接关闭，尝试自动重连"""
        # 🆕 详细断连日志（参考 UserGenie 的溯源日志）
        logger.warning(f"[Doubao ASR] ❌ 连接断开: code={close_code}, reason='{close_reason}'")
        logger.warning(f"[Doubao ASR] 状态: manual_close={self._is_manual_close}, transcript_len={len(self._full_transcript)}, reconnect_attempts={self._reconnect_attempts}")
        
        # 分析断连原因
        if close_code == 1000:
            logger.info("[Doubao ASR] ✅ 正常关闭 (客户端主动)")
        elif close_code == 1001:
            logger.warning("[Doubao ASR] ⚠️ 对端离开 (Going Away)")
        elif close_code == 1006:
            logger.warning("[Doubao ASR] ⚠️ 异常关闭 (网络问题或服务端超时)")
        elif close_code == 1008:
            logger.error("[Doubao ASR] ❌ 策略违规 (可能是 API Key 问题)")
        elif close_code == 1011:
            logger.error("[Doubao ASR] ❌ 服务端内部错误")
        else:
            logger.warning(f"[Doubao ASR] ⚠️ 未知关闭代码: {close_code}")
        
        if self._is_manual_close:
            logger.info("[Doubao ASR] 手动关闭，不重连")
            return
        
        if not self._auto_reconnect:
            logger.info("[Doubao ASR] 未启用自动重连")
            return
        
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"[Doubao ASR] 已达最大重连次数 ({self._max_reconnect_attempts})，放弃重连")
            self._pending_audio_buffer = []  # 清空缓冲
            return
        
        self._reconnect_attempts += 1
        delay = self._reconnect_delay * self._reconnect_attempts  # 递增延迟
        logger.info(f"[Doubao ASR] {delay}秒后尝试重连 ({self._reconnect_attempts}/{self._max_reconnect_attempts})...")
        
        # 通知外部正在重连
        if self._on_reconnect:
            await self._safe_callback(self._on_reconnect, self._reconnect_attempts, False)
        
        await asyncio.sleep(delay)
        
        # 尝试重连
        success = await self._reconnect()
        
        if success:
            logger.info(f"[Doubao ASR] ✅ 重连成功！")
            self._reconnect_attempts = 0
            
            # 🆕 恢复保存的转录（参考 UserGenie）
            if self._preserved_transcript_before_reconnect:
                logger.info(f"[Doubao ASR] 📝 恢复之前的转录: '{self._preserved_transcript_before_reconnect[:50]}...'")
                # 不需要做什么，_full_transcript 已经保留
                self._preserved_transcript_before_reconnect = ""
            
            # 🆕 发送缓冲的音频
            if self._pending_audio_buffer:
                logger.info(f"[Doubao ASR] 📤 发送 {len(self._pending_audio_buffer)} 个缓冲帧...")
                for buffered_audio in self._pending_audio_buffer:
                    await self.send_audio(buffered_audio)
                self._pending_audio_buffer = []
                logger.info("[Doubao ASR] ✅ 缓冲音频发送完成")
            
            # 通知外部重连成功
            if self._on_reconnect:
                await self._safe_callback(self._on_reconnect, self._reconnect_attempts, True)
        else:
            logger.error(f"[Doubao ASR] ❌ 重连失败 ({self._reconnect_attempts}/{self._max_reconnect_attempts})")
    
    async def _reconnect(self) -> bool:
        """🆕 内部重连方法"""
        try:
            # 关闭旧连接
            if self._ws:
                try:
                    await self._ws.close()
                except Exception as e:
                    logger.debug(f"[Doubao ASR] 重连时关闭旧连接失败: {e}")
                self._ws = None
            
            # 重新连接
            url = self._build_ws_url()
            req_id = str(uuid.uuid4())
            
            headers = {
                'X-Api-Resource-Id': 'volc.bigasr.sauc.duration',
                'X-Api-Request-Id': req_id,
                'X-Api-Access-Key': self.config.access_key,
                'X-Api-App-Key': self.config.app_key,
            }
            
            self._ws = await asyncio.wait_for(
                websockets.connect(url, extra_headers=headers),
                timeout=self.config.connection_timeout
            )
            
            # 重置序列号
            self._seq = 1
            
            # 发送初始化请求
            await self._send_start_request()
            
            # 启动新的接收任务
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            self._is_connected = True
            return True
            
        except Exception as e:
            logger.error(f"[Doubao ASR] 重连失败: {e}")
            return False
    
    async def _handle_response(self, data: bytes):
        """处理服务端响应"""
        try:
            # 尝试直接解析未压缩的 JSON（服务端有时返回未压缩数据）
            if len(data) > 8 and data[8:9] == b'{':
                try:
                    json_str = data[8:].decode('utf-8')
                    logger.info(f"[Doubao ASR] 原始 JSON: {json_str[:200]}...")
                except Exception as e:
                    logger.debug(f"[Doubao ASR] 原始 JSON 解码失败: {e}")
            
            result = DoubaoProtocol.parse_response(data)
            logger.info(f"[Doubao ASR] 解析结果: {result}")
            
            if "error_code" in result:
                error_code = result.get("error_code", 0)
                error_msg = result.get("error_msg", "")
                logger.error(f"[Doubao ASR] 服务端错误: code={error_code}, msg={error_msg}")
                
                # 🆕 特殊处理 8 秒超时错误 - 触发自动重连
                if error_code == 45000081:
                    logger.warning("[Doubao ASR] ⚠️ 检测到 8 秒超时错误，触发自动重连...")
                    self._is_connected = False
                    # 保存当前转录供重连后使用
                    if self._full_transcript:
                        self._preserved_transcript_before_reconnect = self._full_transcript
                        logger.info(f"[Doubao ASR] 📝 保存转录供重连后恢复: '{self._full_transcript[:50]}...'")
                    # 🆕 直接在这里触发重连（不等待 close 事件）
                    asyncio.create_task(self._handle_connection_closed(45000081, "8秒超时"))
                return
            
            payload = result.get("payload", {})
            if payload:
                logger.debug(f"[Doubao ASR] Payload keys: {list(payload.keys())}")
            
            # 检查转录结果
            if "result" in payload:
                asr_result = payload["result"]
                
                # 🆕 检查 audio_info（确认音频是否收到）
                audio_info = payload.get("audio_info", {})
                audio_duration = audio_info.get("duration", 0)
                if audio_duration > 0:
                    logger.info(f"[Doubao ASR] 收到音频: {audio_duration}ms")
                
                # 🔧 从多个可能的位置提取文本
                text = asr_result.get("text", "")
                
                # 检查是否最终结果：优先检查 utterances[0].definite，否则检查 is_final
                is_final = asr_result.get("is_final", False)
                utterances = asr_result.get("utterances", [])
                if utterances and len(utterances) > 0:
                    is_final = utterances[0].get("definite", is_final)
                    # 🔧 尝试从 utterances[0] 获取文本
                    if not text:
                        text = utterances[0].get("text", "")
                    # 🔧 尝试从 utterances[0].additions.fixed_prefix_result 获取
                    if not text:
                        additions = utterances[0].get("additions", {})
                        text = additions.get("fixed_prefix_result", "")
                    # 🔧 尝试从 utterances[0].transcript 获取
                    if not text:
                        text = utterances[0].get("transcript", "")
                
                # 🔧 记录调试信息
                if not text and utterances:
                    logger.warning(f"[Doubao ASR] utterances 存在但无文本: {utterances[0]}")
                
                # 🆕 关键日志：音频收到但没识别出文本
                if not text and audio_duration > 0:
                    logger.warning(f"[Doubao ASR] ⚠️ 收到 {audio_duration}ms 音频但未识别出语音！可能原因: 静音/噪音/音量过低")
                
                if text:
                    logger.info(f"[Doubao ASR] 转录: '{text[:50]}...' (final={is_final})")
                    
                    # 始终更新最新转录（因为服务端可能不发送 final 信号）
                    self._full_transcript = text
                    # 🆕 记录最后一个结果的 final 状态
                    self._last_is_final = is_final
                    
                    if self._on_transcript:
                        await self._safe_callback(self._on_transcript, text, is_final)
                
                # 🆕 检查是否说完 - 使用防抖逻辑避免反复触发
                if is_final and self._on_utterance_end:
                    await self._debounced_utterance_end(text)
        
        except Exception as e:
            logger.error(f"[Doubao ASR] 解析响应失败: {e}")
    
    async def _debounced_utterance_end(self, current_text: str):
        """
        防抖的 utterance_end 调用
        
        策略：收到 is_final=True 后，等待 500ms。如果在此期间收到新的转录，
        则重置计时器。只有 500ms 内没有新转录时，才真正触发 utterance_end。
        
        这样可以避免用户说话时因短暂停顿导致的反复触发。
        """
        # 取消之前的防抖任务
        if self._utterance_end_debounce_task and not self._utterance_end_debounce_task.done():
            self._utterance_end_debounce_task.cancel()
            try:
                await self._utterance_end_debounce_task
            except asyncio.CancelledError:
                pass
        
        # 创建新的防抖任务
        async def delayed_utterance_end():
            await asyncio.sleep(self._utterance_end_debounce_ms / 1000.0)
            
            # 检查文本是否有实质变化（避免重复触发相同内容）
            if current_text == self._last_utterance_end_text:
                logger.debug(f"[Doubao ASR] 防抖：文本未变化，跳过 utterance_end")
                return
            
            self._last_utterance_end_text = current_text
            logger.info(f"[Doubao ASR] 防抖完成，触发 utterance_end: '{current_text[:30]}...'")
            await self._safe_callback(self._on_utterance_end)
        
        self._utterance_end_debounce_task = asyncio.create_task(delayed_utterance_end())
    
    async def _safe_callback(self, callback, *args):
        """安全调用回调"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args)
            else:
                callback(*args)
        except Exception as e:
            logger.error(f"回调执行失败: {e}")
    
    def get_full_transcript(self) -> str:
        """获取完整转录"""
        return self._full_transcript
    
    def update_callbacks(
        self,
        on_transcript: Optional[Callable[[str, bool], Any]] = None,
        on_utterance_end: Optional[Callable[[], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_reconnect: Optional[Callable[[int, bool], Any]] = None
    ):
        """
        更新回调函数（不重新建立连接）
        
        用于复用预热连接时，只更新回调而不断开重连。
        阶段 3 新增：解决首句丢失问题。
        """
        if on_transcript is not None:
            self._on_transcript = on_transcript
        if on_utterance_end is not None:
            self._on_utterance_end = on_utterance_end
        if on_error is not None:
            self._on_error = on_error
        if on_reconnect is not None:
            self._on_reconnect = on_reconnect
        
        logger.debug("[Doubao ASR] 回调函数已更新")
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._is_connected
    
    @property
    def is_processing(self) -> bool:
        """ASR 是否还在处理中（最后结果不是 final）"""
        return self._is_connected and not self._last_is_final


class DoubaoASRService(SpeechService):
    """
    豆包 ASR 同步服务（兼容 SpeechService 接口）
    
    用于批量转录，不是流式的。
    """
    
    def __init__(self, config: Optional[DoubaoASRConfig] = None):
        self.config = config or DoubaoASRConfig()
        logger.info("DoubaoASRService 初始化完成")
    
    def transcribe_audio(
        self,
        audio_file: BinaryIO,
        language: Optional[str] = None
    ) -> str:
        """
        转录音频文件
        
        注意：这是同步接口，内部使用异步实现
        """
        try:
            loop = asyncio.get_running_loop()
            raise RuntimeError("在异步环境中，请使用 DoubaoASR 流式接口")
        except RuntimeError as e:
            if "异步环境" in str(e):
                raise
        
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(
                self._transcribe_async(audio_file, language)
            )
        finally:
            loop.close()
    
    async def _transcribe_async(
        self,
        audio_file: BinaryIO,
        language: Optional[str] = None
    ) -> str:
        """异步转录"""
        config = DoubaoASRConfig(
            app_key=self.config.app_key,
            access_key=self.config.access_key,
            language=language or self.config.language
        )
        
        asr = DoubaoASR(config)
        
        # 读取音频数据
        audio_file.seek(0)
        audio_data = audio_file.read()
        
        result_text = ""
        
        async def on_transcript(text, is_final):
            nonlocal result_text
            if is_final:
                result_text = text
        
        # 开始流式识别
        await asr.start_stream(on_transcript=on_transcript)
        
        # 分块发送音频（每块 3200 bytes = 100ms）
        chunk_size = 3200
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            await asr.send_audio(chunk)
            await asyncio.sleep(0.05)  # 模拟实时发送
        
        # 停止并获取结果
        final_result = await asr.stop_stream()
        
        return final_result or result_text


# 工厂函数
def create_doubao_asr(config: Optional[DoubaoASRConfig] = None) -> DoubaoASR:
    """创建豆包流式 ASR 实例"""
    return DoubaoASR(config)


def create_doubao_asr_service(config: Optional[DoubaoASRConfig] = None) -> DoubaoASRService:
    """创建豆包 ASR 服务实例（兼容 SpeechService 接口）"""
    return DoubaoASRService(config)
