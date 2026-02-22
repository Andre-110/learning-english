"""
False Interruption 恢复机制

借鉴自 FireRedChat 的 Agent Session 打断处理逻辑。

问题：
用户"打断"可能是误触发：
- 咳嗽、清嗓子
- 背景噪音（敲键盘、关门）
- 轻微的语气词（嗯、啊）

解决方案：
1. 当检测到用户说话时，先暂停 AI 播放（不终止）
2. 启动超时计时器
3. 如果超时内无实际语音内容 → 恢复 AI 播放
4. 如果有实际内容 → 确认打断，生成新回复

配置参数：
- timeout: 判定误打断的超时时间（默认 1.5 秒）
- min_words: 最少识别词数才确认打断（默认 1）
- min_duration: 最短语音时长才触发打断（默认 0.3 秒）
"""
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional, Any

from services.utils.logger import get_logger

logger = get_logger("services.false_interruption")


class InterruptionState(Enum):
    """打断状态"""
    IDLE = auto()           # 正常播放
    PAUSED = auto()         # 已暂停，等待判定
    CONFIRMED = auto()      # 确认打断
    RESUMED = auto()        # 恢复播放（误打断）


@dataclass
class InterruptionConfig:
    """打断配置"""
    enabled: bool = True
    timeout: float = 1.5           # 判定超时（秒）
    min_words: int = 1             # 最少词数
    min_duration: float = 0.3      # 最短语音时长（秒）
    auto_resume: bool = True       # 是否自动恢复


@dataclass
class InterruptionContext:
    """打断上下文"""
    state: InterruptionState = InterruptionState.IDLE
    pause_time: Optional[float] = None
    speech_start_time: Optional[float] = None
    accumulated_text: str = ""
    accumulated_duration: float = 0.0
    
    # 回调
    on_pause: Optional[Callable[[], Any]] = None
    on_resume: Optional[Callable[[], Any]] = None
    on_confirmed: Optional[Callable[[str], Any]] = None
    
    # 内部任务
    _timeout_task: Optional[asyncio.Task] = None


class FalseInterruptionHandler:
    """
    误打断处理器
    
    使用方式：
        handler = FalseInterruptionHandler()
        
        # 在 AI 播放时，检测到用户语音活动
        await handler.on_speech_detected(
            on_pause=lambda: audio_player.pause(),
            on_resume=lambda: audio_player.resume(),
            on_confirmed=lambda text: process_user_input(text)
        )
        
        # 用户持续说话时更新
        handler.update_speech(text="I want to", duration=0.5)
        
        # 用户停止说话时
        await handler.on_speech_ended()
    """
    
    def __init__(self, config: Optional[InterruptionConfig] = None):
        self.config = config or InterruptionConfig()
        self._context = InterruptionContext()
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> InterruptionState:
        return self._context.state
    
    @property
    def is_paused(self) -> bool:
        return self._context.state == InterruptionState.PAUSED
    
    async def on_speech_detected(
        self,
        on_pause: Optional[Callable[[], Any]] = None,
        on_resume: Optional[Callable[[], Any]] = None,
        on_confirmed: Optional[Callable[[str], Any]] = None
    ) -> bool:
        """
        检测到用户语音活动时调用
        
        Args:
            on_pause: 暂停播放回调
            on_resume: 恢复播放回调
            on_confirmed: 确认打断回调，参数为用户文本
            
        Returns:
            是否已暂停
        """
        if not self.config.enabled:
            # 直接确认打断
            if on_confirmed:
                await self._call_async(on_confirmed, "")
            return False
        
        async with self._lock:
            if self._context.state != InterruptionState.IDLE:
                return False
            
            # 暂停播放
            self._context.state = InterruptionState.PAUSED
            self._context.pause_time = time.time()
            self._context.speech_start_time = time.time()
            self._context.accumulated_text = ""
            self._context.accumulated_duration = 0.0
            self._context.on_pause = on_pause
            self._context.on_resume = on_resume
            self._context.on_confirmed = on_confirmed
            
            # 调用暂停回调
            if on_pause:
                await self._call_async(on_pause)
            
            # 启动超时任务
            self._context._timeout_task = asyncio.create_task(
                self._timeout_handler()
            )
            
            logger.info(f"[FalseInterruption] 暂停播放，等待判定 (timeout={self.config.timeout}s)")
            return True
    
    def update_speech(self, text: str = "", duration: float = 0.0):
        """
        更新用户语音信息
        
        Args:
            text: 累积的转录文本
            duration: 累积的语音时长
        """
        self._context.accumulated_text = text
        self._context.accumulated_duration = duration
    
    async def on_speech_ended(self) -> InterruptionState:
        """
        用户语音结束时调用
        
        Returns:
            最终状态（CONFIRMED 或 RESUMED）
        """
        async with self._lock:
            if self._context.state != InterruptionState.PAUSED:
                return self._context.state
            
            # 取消超时任务
            if self._context._timeout_task:
                self._context._timeout_task.cancel()
                self._context._timeout_task = None
            
            # 判定是否为真正打断
            is_real_interruption = self._check_real_interruption()
            
            if is_real_interruption:
                return await self._confirm_interruption()
            else:
                return await self._resume_playback()
    
    def _check_real_interruption(self) -> bool:
        """检查是否为真正的打断"""
        text = self._context.accumulated_text.strip()
        duration = self._context.accumulated_duration
        
        # 检查最小词数
        if self.config.min_words > 0:
            words = text.split()
            if len(words) < self.config.min_words:
                logger.debug(f"[FalseInterruption] 词数不足: {len(words)} < {self.config.min_words}")
                return False
        
        # 检查最小时长
        if duration < self.config.min_duration:
            logger.debug(f"[FalseInterruption] 时长不足: {duration:.2f}s < {self.config.min_duration}s")
            return False
        
        # 检查是否只是语气词
        filler_words = {'um', 'uh', 'eh', 'ah', 'oh', 'hmm', 'er', 'like', '嗯', '啊', '哦', '额'}
        words_lower = {w.lower() for w in text.split()}
        if words_lower.issubset(filler_words):
            logger.debug(f"[FalseInterruption] 只有语气词: {text}")
            return False
        
        return True
    
    async def _confirm_interruption(self) -> InterruptionState:
        """确认打断"""
        self._context.state = InterruptionState.CONFIRMED
        text = self._context.accumulated_text
        
        logger.info(f"[FalseInterruption] 确认打断，用户输入: '{text[:30]}...'")
        
        if self._context.on_confirmed:
            await self._call_async(self._context.on_confirmed, text)
        
        return InterruptionState.CONFIRMED
    
    async def _resume_playback(self) -> InterruptionState:
        """恢复播放"""
        if not self.config.auto_resume:
            return await self._confirm_interruption()
        
        self._context.state = InterruptionState.RESUMED
        
        pause_duration = time.time() - (self._context.pause_time or time.time())
        logger.info(f"[FalseInterruption] 误打断，恢复播放 (暂停了 {pause_duration:.2f}s)")
        
        if self._context.on_resume:
            await self._call_async(self._context.on_resume)
        
        return InterruptionState.RESUMED
    
    async def _timeout_handler(self):
        """超时处理"""
        try:
            await asyncio.sleep(self.config.timeout)
            
            async with self._lock:
                if self._context.state != InterruptionState.PAUSED:
                    return
                
                # 超时，判定是否为误打断
                is_real = self._check_real_interruption()
                
                if is_real:
                    await self._confirm_interruption()
                else:
                    await self._resume_playback()
                    
        except asyncio.CancelledError:
            pass
    
    async def _call_async(self, func: Callable, *args):
        """调用回调（支持同步和异步）"""
        try:
            result = func(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"[FalseInterruption] 回调执行失败: {e}")
    
    def reset(self):
        """重置状态"""
        if self._context._timeout_task:
            self._context._timeout_task.cancel()
        
        self._context = InterruptionContext()
        logger.debug("[FalseInterruption] 状态已重置")


# 全局单例
_handler_instance: Optional[FalseInterruptionHandler] = None


def get_false_interruption_handler(
    config: Optional[InterruptionConfig] = None
) -> FalseInterruptionHandler:
    """获取全局处理器实例"""
    global _handler_instance
    
    if _handler_instance is None:
        _handler_instance = FalseInterruptionHandler(config)
    
    return _handler_instance
