"""
Doubao ASR 热备份连接池

实现真正的热备份：
- 同时维护 primary + standby 两个连接
- primary 断开时立即切换到 standby（0 延迟）
- 切换后异步建立新的 standby
- standby 通过 keepalive 静音包保持连接

参考：UserGenie.ai 的热备份实现
"""

import asyncio
from typing import Optional, Callable, Any
from dataclasses import dataclass

from services.doubao_asr import DoubaoASR, DoubaoASRConfig
from services.utils.logger import get_logger

logger = get_logger("services.doubao_asr_pool")


@dataclass
class PoolConfig:
    """连接池配置"""
    # Keepalive 配置
    keepalive_interval: float = 5.0  # 每 5 秒发送一次静音包
    keepalive_audio_size: int = 320  # 10ms 的静音 PCM (16kHz * 16bit * 10ms)
    
    # 切换配置
    switch_timeout: float = 2.0  # 切换超时时间
    
    # 重建配置
    rebuild_delay: float = 0.5  # 切换后多久开始重建 standby


class DoubaoASRPool:
    """
    Doubao ASR 热备份连接池
    
    使用示例：
    ```python
    pool = DoubaoASRPool()
    
    async def on_transcript(text, is_final):
        print(f"转录: {text}")
    
    await pool.start(on_transcript=on_transcript)
    
    while recording:
        await pool.send_audio(audio_chunk)
    
    result = await pool.stop()
    ```
    """
    
    def __init__(
        self,
        asr_config: Optional[DoubaoASRConfig] = None,
        pool_config: Optional[PoolConfig] = None
    ):
        self.asr_config = asr_config or DoubaoASRConfig()
        self.pool_config = pool_config or PoolConfig()
        
        # 连接实例
        self._primary: Optional[DoubaoASR] = None
        self._standby: Optional[DoubaoASR] = None
        
        # 状态
        self._is_running = False
        self._is_switching = False
        
        # 回调
        self._on_transcript: Optional[Callable] = None
        self._on_utterance_end: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        self._on_switch: Optional[Callable] = None  # 切换通知回调
        
        # Keepalive 任务
        self._keepalive_task: Optional[asyncio.Task] = None
        
        # 静音音频（用于 keepalive）
        self._silence_audio = bytes(self.pool_config.keepalive_audio_size)
        
        # 统计
        self._switch_count = 0
        self._total_keepalives_sent = 0
        
        logger.info("[ASR Pool] 初始化完成")
    
    async def start(
        self,
        on_transcript: Optional[Callable[[str, bool], Any]] = None,
        on_utterance_end: Optional[Callable[[], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_switch: Optional[Callable[[int], Any]] = None  # 切换回调 (switch_count)
    ) -> bool:
        """
        启动连接池（同时建立 primary + standby）
        
        Args:
            on_transcript: 转录回调
            on_utterance_end: 说完回调
            on_error: 错误回调
            on_switch: 切换回调（当发生热切换时通知）
        
        Returns:
            是否成功启动
        """
        if self._is_running:
            logger.warning("[ASR Pool] 已在运行中")
            return True
        
        self._on_transcript = on_transcript
        self._on_utterance_end = on_utterance_end
        self._on_error = on_error
        self._on_switch = on_switch
        
        try:
            # 1. 建立 primary 连接
            logger.info("[ASR Pool] 🔵 建立 primary 连接...")
            self._primary = DoubaoASR(self.asr_config)
            primary_success = await self._primary.start_stream(
                on_transcript=self._handle_primary_transcript,
                on_utterance_end=self._handle_utterance_end,
                on_error=self._handle_primary_error,
                on_reconnect=self._handle_primary_reconnect
            )
            
            if not primary_success:
                logger.error("[ASR Pool] ❌ primary 连接失败")
                return False
            
            logger.info("[ASR Pool] ✅ primary 连接成功")
            
            # 2. 异步建立 standby 连接（不阻塞）
            asyncio.create_task(self._build_standby())
            
            # 3. 启动 keepalive 任务
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            
            self._is_running = True
            logger.info("[ASR Pool] ✅ 连接池启动成功")
            return True
            
        except Exception as e:
            logger.error(f"[ASR Pool] ❌ 启动失败: {e}")
            return False
    
    async def _build_standby(self):
        """异步建立 standby 连接"""
        try:
            logger.info("[ASR Pool] 🟡 建立 standby 连接...")
            self._standby = DoubaoASR(self.asr_config)
            
            # standby 不需要处理转录结果，只需要保持连接
            async def standby_transcript(text, is_final):
                # 忽略 standby 的转录结果
                pass
            
            standby_success = await self._standby.start_stream(
                on_transcript=standby_transcript,
                on_utterance_end=None,
                on_error=self._handle_standby_error,
                on_reconnect=self._handle_standby_reconnect
            )
            
            if standby_success:
                logger.info("[ASR Pool] ✅ standby 连接成功（热备份就绪）")
            else:
                logger.warning("[ASR Pool] ⚠️ standby 连接失败，将在下次尝试重建")
                self._standby = None
                
        except Exception as e:
            logger.error(f"[ASR Pool] ❌ standby 建立失败: {e}")
            self._standby = None
    
    async def _keepalive_loop(self):
        """Keepalive 循环：定期发送静音包保持 standby 连接"""
        logger.info(f"[ASR Pool] 🔄 Keepalive 任务启动 (间隔 {self.pool_config.keepalive_interval}s)")
        
        while self._is_running:
            try:
                await asyncio.sleep(self.pool_config.keepalive_interval)
                
                if self._standby and self._standby.is_connected:
                    await self._standby.send_audio(self._silence_audio)
                    self._total_keepalives_sent += 1
                    
                    if self._total_keepalives_sent % 10 == 0:
                        logger.debug(f"[ASR Pool] 💓 Keepalive #{self._total_keepalives_sent} sent to standby")
                elif self._standby is None and self._is_running and not self._is_switching:
                    # standby 不存在，尝试重建
                    logger.info("[ASR Pool] 🔄 standby 不存在，尝试重建...")
                    await self._build_standby()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[ASR Pool] Keepalive 错误: {e}")
        
        logger.info("[ASR Pool] Keepalive 任务结束")
    
    async def send_audio(self, audio_data: bytes) -> bool:
        """
        发送音频数据到 primary 连接
        
        如果 primary 断开，会触发自动切换
        """
        if not self._is_running:
            return False
        
        if self._is_switching:
            # 切换中，缓冲音频（DoubaoASR 内部会处理）
            if self._primary:
                return await self._primary.send_audio(audio_data)
            return False
        
        if self._primary and self._primary.is_connected:
            return await self._primary.send_audio(audio_data)
        else:
            # primary 断开，触发切换
            logger.warning("[ASR Pool] ⚠️ primary 发送失败，触发热切换")
            await self._switch_to_standby()
            
            # 切换后重新发送
            if self._primary and self._primary.is_connected:
                return await self._primary.send_audio(audio_data)
            return False
    
    async def _switch_to_standby(self):
        """热切换：将 standby 提升为 primary"""
        if self._is_switching:
            logger.debug("[ASR Pool] 已在切换中，跳过")
            return
        
        self._is_switching = True
        self._switch_count += 1
        
        try:
            logger.info(f"[ASR Pool] 🔄 热切换开始 (第 {self._switch_count} 次)...")
            
            # 1. 关闭旧的 primary（如果还存在）
            old_primary = self._primary
            if old_primary:
                try:
                    await old_primary.stop_stream()
                except:
                    pass
            
            # 2. 检查 standby 是否可用
            if self._standby and self._standby.is_connected:
                # 🔥 核心：将 standby 提升为 primary
                self._primary = self._standby
                self._standby = None
                
                # 重新绑定回调
                self._primary._on_transcript = self._handle_primary_transcript
                self._primary._on_utterance_end = self._handle_utterance_end
                self._primary._on_error = self._handle_primary_error
                self._primary._on_reconnect = self._handle_primary_reconnect
                
                logger.info(f"[ASR Pool] ✅ 热切换成功！standby → primary (0ms 延迟)")
                
                # 通知外部
                if self._on_switch:
                    try:
                        if asyncio.iscoroutinefunction(self._on_switch):
                            await self._on_switch(self._switch_count)
                        else:
                            self._on_switch(self._switch_count)
                    except Exception as e:
                        logger.warning(f"[ASR Pool] on_switch 回调失败: {e}")
                
                # 3. 异步重建 standby
                asyncio.create_task(self._delayed_rebuild_standby())
                
            else:
                # standby 不可用，需要重建 primary
                logger.warning("[ASR Pool] ⚠️ standby 不可用，重建 primary...")
                self._primary = DoubaoASR(self.asr_config)
                success = await self._primary.start_stream(
                    on_transcript=self._handle_primary_transcript,
                    on_utterance_end=self._handle_utterance_end,
                    on_error=self._handle_primary_error,
                    on_reconnect=self._handle_primary_reconnect
                )
                
                if success:
                    logger.info("[ASR Pool] ✅ primary 重建成功")
                else:
                    logger.error("[ASR Pool] ❌ primary 重建失败")
                
                # 同时重建 standby
                asyncio.create_task(self._delayed_rebuild_standby())
                
        finally:
            self._is_switching = False
    
    async def _delayed_rebuild_standby(self):
        """延迟重建 standby"""
        await asyncio.sleep(self.pool_config.rebuild_delay)
        if self._is_running and self._standby is None:
            await self._build_standby()
    
    async def _handle_primary_transcript(self, text: str, is_final: bool):
        """处理 primary 的转录结果"""
        if self._on_transcript:
            try:
                if asyncio.iscoroutinefunction(self._on_transcript):
                    await self._on_transcript(text, is_final)
                else:
                    self._on_transcript(text, is_final)
            except Exception as e:
                logger.warning(f"[ASR Pool] transcript 回调失败: {e}")
    
    async def _handle_utterance_end(self):
        """处理说完事件"""
        if self._on_utterance_end:
            try:
                if asyncio.iscoroutinefunction(self._on_utterance_end):
                    await self._on_utterance_end()
                else:
                    self._on_utterance_end()
            except Exception as e:
                logger.warning(f"[ASR Pool] utterance_end 回调失败: {e}")
    
    async def _handle_primary_error(self, error: Exception):
        """处理 primary 错误"""
        logger.error(f"[ASR Pool] primary 错误: {error}")
        # 触发切换
        await self._switch_to_standby()
        
        if self._on_error:
            try:
                if asyncio.iscoroutinefunction(self._on_error):
                    await self._on_error(error)
                else:
                    self._on_error(error)
            except:
                pass
    
    async def _handle_primary_reconnect(self, attempt: int, success: bool):
        """处理 primary 重连事件"""
        if not success:
            # primary 开始重连，触发热切换
            logger.info("[ASR Pool] primary 开始重连，触发热切换...")
            await self._switch_to_standby()
    
    async def _handle_standby_error(self, error: Exception):
        """处理 standby 错误"""
        logger.warning(f"[ASR Pool] standby 错误: {error}，将重建")
        self._standby = None
    
    async def _handle_standby_reconnect(self, attempt: int, success: bool):
        """处理 standby 重连事件"""
        if not success:
            logger.warning("[ASR Pool] standby 重连失败，标记为不可用")
            self._standby = None
    
    async def stop(self) -> str:
        """停止连接池，返回最终转录"""
        return await self.stop_stream()
    
    async def stop_stream(self) -> str:
        """停止连接池，返回最终转录（兼容 DoubaoASR 接口）"""
        self._is_running = False
        
        # 停止 keepalive
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        
        result = ""
        
        # 停止 primary
        if self._primary:
            try:
                result = await self._primary.stop_stream()
            except:
                pass
            self._primary = None
        
        # 停止 standby
        if self._standby:
            try:
                await self._standby.stop_stream()
            except:
                pass
            self._standby = None
        
        logger.info(f"[ASR Pool] 已停止，共切换 {self._switch_count} 次，发送 {self._total_keepalives_sent} 个 keepalive")
        return result
    
    def get_full_transcript(self) -> str:
        """获取完整转录"""
        if self._primary:
            return self._primary.get_full_transcript()
        return ""
    
    @property
    def is_connected(self) -> bool:
        """是否有可用连接"""
        return self._is_running and (
            (self._primary and self._primary.is_connected) or
            (self._standby and self._standby.is_connected)
        )
    
    @property
    def is_processing(self) -> bool:
        """ASR 是否还在处理中（最后结果不是 final）"""
        if self._primary:
            return self._primary.is_processing
        return False
    
    @property
    def has_standby(self) -> bool:
        """是否有备用连接就绪"""
        return self._standby is not None and self._standby.is_connected
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "is_running": self._is_running,
            "primary_connected": self._primary.is_connected if self._primary else False,
            "standby_connected": self._standby.is_connected if self._standby else False,
            "switch_count": self._switch_count,
            "keepalives_sent": self._total_keepalives_sent,
        }


# 工厂函数
def create_asr_pool(
    asr_config: Optional[DoubaoASRConfig] = None,
    pool_config: Optional[PoolConfig] = None
) -> DoubaoASRPool:
    """创建 ASR 热备份连接池"""
    return DoubaoASRPool(asr_config, pool_config)
