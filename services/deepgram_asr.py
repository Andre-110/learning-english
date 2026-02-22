"""
Deepgram 流式 ASR 服务

提供实时流式语音转文字功能，替代批量 ASR（Whisper）以降低延迟。

优势：
- 边说边转：用户说话时就开始转录
- 延迟降低：省去等待完整音频的时间（~1.5s）
- 服务端 VAD：Deepgram 内置 utterance_end 检测

使用方式：
1. 创建 DeepgramASR 实例
2. 调用 start_stream() 开始流式连接
3. 调用 send_audio() 发送音频块
4. 监听 on_transcript 回调获取转录结果
5. 调用 stop_stream() 结束
"""
import asyncio
from typing import Optional, Callable, Any
from dataclasses import dataclass

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("services.deepgram_asr")
settings = Settings()


@dataclass
class DeepgramConfig:
    """Deepgram 配置"""
    
    # API 配置
    api_key: str = ""
    
    # 模型配置
    model: str = "nova-2"  # nova-2 是最新最快的模型
    language: str = "en"
    
    # 流式配置
    encoding: str = "linear16"  # PCM 16-bit
    sample_rate: int = 16000
    channels: int = 1
    
    # VAD 配置 - 服务端静默检测 (🆕 完全对齐 UserGenie)
    endpointing: int = 1000  # ms，端点检测静默时间（UserGenie: 1000ms）
    utterance_end_ms: int = 2000  # ms，话语结束检测静默时间（UserGenie: 2000ms）
    
    # 其他配置
    interim_results: bool = True  # 是否返回中间结果
    punctuate: bool = True  # 是否添加标点
    smart_format: bool = True  # 智能格式化
    
    def __post_init__(self):
        if not self.api_key:
            self.api_key = getattr(settings, 'deepgram_api_key', '') or ''


class DeepgramASR:
    """
    Deepgram 流式 ASR 服务
    
    使用示例：
    ```python
    asr = DeepgramASR()
    
    async def on_transcript(text, is_final):
        print(f"{'[Final]' if is_final else '[Interim]'} {text}")
    
    async def on_utterance_end():
        print("用户说完了")
    
    await asr.start_stream(
        on_transcript=on_transcript,
        on_utterance_end=on_utterance_end
    )
    
    # 持续发送音频块
    while recording:
        await asr.send_audio(audio_chunk)
    
    await asr.stop_stream()
    ```
    """
    
    def __init__(self, config: Optional[DeepgramConfig] = None):
        self.config = config or DeepgramConfig()
        
        if not self.config.api_key:
            raise ValueError("Deepgram API Key 未配置，请在 .env 中设置 DEEPGRAM_API_KEY")
        
        # 创建 Deepgram 客户端
        client_options = DeepgramClientOptions(
            verbose=False
        )
        self.client = DeepgramClient(self.config.api_key, client_options)
        
        # 流式连接
        self._connection = None
        self._is_connected = False
        
        # 回调函数
        self._on_transcript: Optional[Callable] = None
        self._on_utterance_end: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        self._on_reconnect: Optional[Callable] = None  # 🆕 重连回调
        
        # 累积转录结果
        self._full_transcript = ""
        
        # 🆕 自动重连配置
        self._auto_reconnect = True  # 是否启用自动重连
        self._max_reconnect_attempts = 3  # 最大重连次数
        self._reconnect_delay = 1.0  # 重连延迟（秒，递增）
        self._reconnect_attempts = 0  # 当前重连次数
        self._is_manual_close = False  # 是否手动关闭（不需要重连）
        self._pending_audio_buffer = []  # 🆕 重连期间的音频缓冲
        self._max_buffer_size = 300  # 🆕 参考 UserGenie: 增加缓冲（约 10 秒音频）
        
        # 🆕 参考 UserGenie: 保存重连前的转录，避免丢失
        self._preserved_transcript_before_reconnect = ""
        
        logger.info(f"DeepgramASR 初始化完成: model={self.config.model}, language={self.config.language}")
    
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
            on_reconnect: 重连回调 (attempt_count, is_success)
        
        Returns:
            是否成功连接
        """
        if self._is_connected:
            logger.warning("已有活跃连接，先关闭")
            self._is_manual_close = True
            await self.stop_stream()
        
        self._on_transcript = on_transcript
        self._on_utterance_end = on_utterance_end
        self._on_error = on_error
        self._on_reconnect = on_reconnect
        self._full_transcript = ""
        self._is_manual_close = False  # 重置手动关闭标志
        self._reconnect_attempts = 0  # 重置重连次数
        
        try:
            # 创建 Live 连接
            self._connection = self.client.listen.asynclive.v("1")
            
            # 注册事件处理器
            self._connection.on(LiveTranscriptionEvents.Transcript, self._handle_transcript)
            self._connection.on(LiveTranscriptionEvents.UtteranceEnd, self._handle_utterance_end)
            self._connection.on(LiveTranscriptionEvents.Error, self._handle_error)
            self._connection.on(LiveTranscriptionEvents.Close, self._handle_close)
            
            # 配置选项 - 启用服务端 VAD (utterance_end)
            options = LiveOptions(
                model=self.config.model,
                language=self.config.language,
                encoding=self.config.encoding,
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                interim_results=self.config.interim_results,
                punctuate=self.config.punctuate,
                smart_format=self.config.smart_format,
                # 🆕 启用服务端 VAD - 由 Deepgram 判断用户说完
                endpointing=self.config.endpointing,
                utterance_end_ms=str(self.config.utterance_end_ms),  # 必须是字符串
                vad_events=True,  # 🆕 启用 VAD 事件
            )
            
            # 启动连接
            started = await self._connection.start(options)
            
            if started:
                self._is_connected = True
                logger.info("[Deepgram] 流式连接已建立")
                return True
            else:
                logger.error("[Deepgram] 连接启动失败")
                return False
                
        except Exception as e:
            logger.error(f"[Deepgram] 连接失败: {e}")
            if self._on_error:
                await self._on_error(e)
            return False
    
    async def send_audio(self, audio_data: bytes) -> bool:
        """
        发送音频数据块
        
        Args:
            audio_data: PCM 音频数据 (16-bit, mono)
        
        Returns:
            是否发送成功
        """
        if not self._is_connected or not self._connection:
            # 🆕 未连接时缓冲音频（用于重连后发送）
            if len(self._pending_audio_buffer) < self._max_buffer_size:
                self._pending_audio_buffer.append(audio_data)
                if len(self._pending_audio_buffer) % 20 == 1:
                    logger.info(f"[Deepgram] 未连接，缓冲音频 #{len(self._pending_audio_buffer)}")
            else:
                # 缓冲满，丢弃最老的
                self._pending_audio_buffer.pop(0)
                self._pending_audio_buffer.append(audio_data)
            return False
        
        try:
            await self._connection.send(audio_data)
            # 每 10 次发送记录一次（避免日志过多）
            if not hasattr(self, '_send_count'):
                self._send_count = 0
            self._send_count += 1
            if self._send_count % 10 == 1:
                logger.info(f"[Deepgram] 发送音频 #{self._send_count}, {len(audio_data)} bytes")
            return True
        except Exception as e:
            logger.error(f"[Deepgram] 发送音频失败: {e}")
            # 🔧 修复：发送失败标记连接不可用，避免后续帧继续发送到死连接
            self._is_connected = False
            # 缓冲起来等重连
            if len(self._pending_audio_buffer) < self._max_buffer_size:
                self._pending_audio_buffer.append(audio_data)
            return False
    
    async def stop_stream(self) -> str:
        """
        停止流式 ASR 连接

        Returns:
            完整转录结果
        """
        # 🔧 修复：防止重复调用
        if self._is_manual_close and not self._is_connected and not self._connection:
            logger.debug("[Deepgram] stop_stream 已调用过，跳过重复调用")
            return self._full_transcript

        self._is_manual_close = True  # 标记手动关闭，不触发重连
        
        if self._connection and self._is_connected:
            try:
                await self._connection.finish()
            except Exception as e:
                logger.warning(f"[Deepgram] finish() 失败，尝试强制关闭: {e}")
                try:
                    if hasattr(self._connection, '_socket') and self._connection._socket:
                        await self._connection._socket.close()
                except Exception as e2:
                    logger.warning(f"[Deepgram] 强制关闭也失败: {e2}")
        
        self._is_connected = False
        self._connection = None
        self._pending_audio_buffer = []  # 🆕 清空缓冲
        
        result = self._full_transcript
        logger.info(f"[Deepgram] 流式连接已关闭，完整转录: {result[:50]}...")
        
        return result
    
    def get_full_transcript(self) -> str:
        """获取当前累积的完整转录"""
        return self._full_transcript
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._is_connected
    
    @property
    def preserved_transcript(self) -> str:
        """获取保存的重连前转录（参考 UserGenie）"""
        return self._preserved_transcript_before_reconnect
    
    @property
    def reconnect_attempts(self) -> int:
        """当前重连次数"""
        return self._reconnect_attempts
    
    # ==================== 事件处理器 ====================
    
    async def _handle_transcript(self, *args, **kwargs):
        """处理转录事件"""
        try:
            result = kwargs.get("result") or (args[1] if len(args) > 1 else None)
            if not result:
                return
            
            # 获取转录文本
            channel = result.channel
            alternatives = channel.alternatives
            if not alternatives:
                return
            
            transcript = alternatives[0].transcript
            is_final = result.is_final
            
            if not transcript:
                return
            
            # 🆕 记录转录结果
            logger.info(f"[Deepgram] 转录: '{transcript[:50]}...' (final={is_final})")
            
            # 如果是最终结果，累积到完整转录
            if is_final:
                # 🆕 参考 UserGenie: 如果有保存的重连前转录，先拼接
                if self._preserved_transcript_before_reconnect:
                    prefix = self._preserved_transcript_before_reconnect
                    transcript = f"{prefix} {transcript}"
                    logger.info(f"[Deepgram] 拼接保存的转录: '{transcript[:50]}...'")
                    self._preserved_transcript_before_reconnect = ""  # 清空，只拼接一次
                
                if self._full_transcript:
                    self._full_transcript += " " + transcript
                else:
                    self._full_transcript = transcript
            
            # 调用回调
            if self._on_transcript:
                if asyncio.iscoroutinefunction(self._on_transcript):
                    await self._on_transcript(transcript, is_final)
                else:
                    self._on_transcript(transcript, is_final)
                    
        except Exception as e:
            logger.error(f"[Deepgram] 处理转录事件失败: {e}")
    
    async def _handle_utterance_end(self, *args, **kwargs):
        """处理 utterance_end 事件（用户说完）"""
        logger.info("[Deepgram] 检测到 utterance_end（用户说完）")
        
        if self._on_utterance_end:
            if asyncio.iscoroutinefunction(self._on_utterance_end):
                await self._on_utterance_end()
            else:
                self._on_utterance_end()
    
    async def _handle_error(self, *args, **kwargs):
        """处理错误事件"""
        error = kwargs.get("error") or (args[1] if len(args) > 1 else None)
        logger.error(f"[Deepgram] 错误: {error}")
        
        if self._on_error and error:
            if asyncio.iscoroutinefunction(self._on_error):
                await self._on_error(error)
            else:
                self._on_error(error)
    
    async def _handle_close(self, *args, **kwargs):
        """处理连接关闭事件"""
        # 🆕 提取关闭代码和原因（用于诊断断连原因）
        close_code = kwargs.get("code") or (args[1] if len(args) > 1 else 1006)
        close_reason = kwargs.get("reason") or (args[2] if len(args) > 2 else "unknown")
        
        # 🆕 详细断连日志（参考 UserGenie 的溯源日志）
        logger.warning(f"[Deepgram] ❌ 连接断开: code={close_code}, reason='{close_reason}'")
        logger.warning(f"[Deepgram] 状态: manual_close={self._is_manual_close}, transcript_len={len(self._full_transcript)}, reconnect_attempts={self._reconnect_attempts}")
        
        # 分析断连原因
        if close_code == 1000:
            logger.info("[Deepgram] ✅ 正常关闭 (客户端主动)")
        elif close_code == 1001:
            logger.warning("[Deepgram] ⚠️ 对端离开 (Going Away)")
        elif close_code == 1006:
            logger.warning("[Deepgram] ⚠️ 异常关闭 (网络问题或服务端超时)")
        elif close_code == 1008:
            logger.error("[Deepgram] ❌ 策略违规 (可能是 API Key 问题)")
        elif close_code == 1011:
            logger.error("[Deepgram] ❌ 服务端内部错误")
        else:
            logger.warning(f"[Deepgram] ⚠️ 未知关闭代码: {close_code}")
        
        self._is_connected = False
        
        # 🆕 自动重连逻辑
        if not self._is_manual_close and self._auto_reconnect:
            if self._reconnect_attempts < self._max_reconnect_attempts:
                self._reconnect_attempts += 1
                delay = self._reconnect_delay * self._reconnect_attempts  # 递增延迟
                logger.info(f"[Deepgram] {delay}秒后尝试重连 ({self._reconnect_attempts}/{self._max_reconnect_attempts})...")
                
                # 🆕 参考 UserGenie: 保存重连前的转录，避免丢失
                if self._full_transcript.strip():
                    self._preserved_transcript_before_reconnect = self._full_transcript.strip()
                    logger.info(f"[Deepgram] 保存重连前转录: '{self._preserved_transcript_before_reconnect[:50]}...'")
                
                # 通知外部正在重连
                if self._on_reconnect:
                    try:
                        if asyncio.iscoroutinefunction(self._on_reconnect):
                            await self._on_reconnect(self._reconnect_attempts, False)
                        else:
                            self._on_reconnect(self._reconnect_attempts, False)
                    except Exception as e:
                        logger.warning(f"[Deepgram] 重连回调失败: {e}")
                
                await asyncio.sleep(delay)
                
                # 尝试重连
                success = await self._reconnect()
                
                if success:
                    logger.info(f"[Deepgram] 重连成功！")
                    self._reconnect_attempts = 0
                    
                    # 🆕 参考 UserGenie: 恢复保存的转录作为前缀
                    if self._preserved_transcript_before_reconnect:
                        logger.info(f"[Deepgram] 恢复保存的转录: '{self._preserved_transcript_before_reconnect[:50]}...'")
                        # _full_transcript 将在下次 final result 时与新结果合并
                    
                    # 🆕 发送缓冲的音频
                    if self._pending_audio_buffer:
                        logger.info(f"[Deepgram] 发送 {len(self._pending_audio_buffer)} 个缓冲帧...")
                        for buffered_audio in self._pending_audio_buffer:
                            await self.send_audio(buffered_audio)
                        self._pending_audio_buffer = []
                    
                    # 通知外部重连成功
                    if self._on_reconnect:
                        try:
                            if asyncio.iscoroutinefunction(self._on_reconnect):
                                await self._on_reconnect(self._reconnect_attempts, True)
                            else:
                                self._on_reconnect(self._reconnect_attempts, True)
                        except Exception as e:
                            logger.warning(f"[Deepgram] 重连成功回调失败: {e}")
                else:
                    logger.error(f"[Deepgram] 重连失败 ({self._reconnect_attempts}/{self._max_reconnect_attempts})")
            else:
                logger.error(f"[Deepgram] 已达最大重连次数 ({self._max_reconnect_attempts})，放弃重连")
                self._pending_audio_buffer = []  # 清空缓冲
    
    async def _reconnect(self) -> bool:
        """
        内部重连方法
        
        Returns:
            是否重连成功
        """
        try:
            # 创建新连接
            self._connection = self.client.listen.asynclive.v("1")
            
            # 注册事件处理器
            self._connection.on(LiveTranscriptionEvents.Transcript, self._handle_transcript)
            self._connection.on(LiveTranscriptionEvents.UtteranceEnd, self._handle_utterance_end)
            self._connection.on(LiveTranscriptionEvents.Error, self._handle_error)
            self._connection.on(LiveTranscriptionEvents.Close, self._handle_close)
            
            # 配置选项
            from deepgram import LiveOptions
            options = LiveOptions(
                model=self.config.model,
                language=self.config.language,
                encoding=self.config.encoding,
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                interim_results=self.config.interim_results,
                punctuate=self.config.punctuate,
                smart_format=self.config.smart_format,
                endpointing=self.config.endpointing,
                utterance_end_ms=str(self.config.utterance_end_ms),
                vad_events=True,
            )
            
            started = await self._connection.start(options)
            
            if started:
                self._is_connected = True
                return True
            return False
            
        except Exception as e:
            logger.error(f"[Deepgram] 重连异常: {e}")
            return False


# 工厂函数
def create_deepgram_asr(config: Optional[DeepgramConfig] = None) -> DeepgramASR:
    """创建 Deepgram ASR 实例"""
    return DeepgramASR(config)
