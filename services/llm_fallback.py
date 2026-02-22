"""
LLM 备用机制 - 主服务超时自动切换备用服务

功能：
1. 主服务调用（带超时）
2. 超时或失败时自动切换到备用服务
3. 性能指标记录

参考：UserGenie callLLMWithFallback 机制
"""
import time
import asyncio
from typing import Optional, Generator, AsyncGenerator, List, Dict, Any, Union
from dataclasses import dataclass

from services.utils.logger import get_logger

logger = get_logger("services.llm_fallback")


@dataclass
class LLMCallResult:
    """LLM 调用结果"""
    success: bool
    used_backup: bool
    latency_ms: float
    error: Optional[str] = None


class LLMFallbackService:
    """
    带备用机制的 LLM 服务
    
    使用方式：
        fallback = LLMFallbackService(
            primary_service=openrouter_service,
            backup_service=qwen_service,
            timeout_seconds=5.0
        )
        
        # 非流式调用
        result = await fallback.call_with_text(messages)
        
        # 流式调用
        async for chunk in fallback.call_with_text_stream(messages):
            print(chunk)
    """
    
    def __init__(
        self,
        primary_service,
        backup_service=None,
        timeout_seconds: float = 5.0,
        primary_name: str = "Primary",
        backup_name: str = "Backup"
    ):
        self.primary = primary_service
        self.backup = backup_service
        self.timeout = timeout_seconds
        self.primary_name = primary_name
        self.backup_name = backup_name
        
        # 统计
        self.stats = {
            "primary_success": 0,
            "primary_timeout": 0,
            "primary_error": 0,
            "backup_success": 0,
            "backup_error": 0,
        }
        
        logger.info(
            f"[LLM Fallback] 初始化: primary={primary_name}, "
            f"backup={backup_name if backup_service else 'None'}, "
            f"timeout={timeout_seconds}s"
        )
    
    def call_with_text_stream_sync(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[str, None, None]:
        """
        同步流式调用（带超时备用）
        
        注意：这个版本使用同步生成器，超时检测在第一个 chunk 上
        
        Yields:
            文本片段
        """
        start_time = time.time()
        used_backup = False
        
        try:
            # 尝试主服务
            logger.info(f"[LLM Fallback] 调用主服务 ({self.primary_name})...")
            
            first_chunk_received = False
            first_chunk_time = None
            
            for chunk in self.primary.call_with_text_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                conversation_history=conversation_history
            ):
                if not first_chunk_received:
                    first_chunk_received = True
                    first_chunk_time = time.time() - start_time
                    
                    # 检查首 token 是否超时
                    if first_chunk_time > self.timeout:
                        logger.warning(
                            f"[LLM Fallback] 主服务首 token 超时: {first_chunk_time:.2f}s > {self.timeout}s"
                        )
                        self.stats["primary_timeout"] += 1
                        raise TimeoutError(f"First token timeout: {first_chunk_time:.2f}s")
                    
                    logger.info(f"[LLM Fallback] 主服务首 token: {first_chunk_time*1000:.0f}ms")
                
                yield chunk
            
            # 主服务成功
            elapsed = time.time() - start_time
            self.stats["primary_success"] += 1
            logger.info(f"[LLM Fallback] 主服务完成, 耗时: {elapsed:.2f}s")
            return
            
        except (TimeoutError, Exception) as e:
            elapsed = time.time() - start_time
            error_type = "timeout" if isinstance(e, TimeoutError) else "error"
            
            if error_type == "error":
                self.stats["primary_error"] += 1
            
            logger.warning(
                f"[LLM Fallback] 主服务失败 ({error_type}): {e}, "
                f"耗时: {elapsed:.2f}s, 切换备用服务..."
            )
            
            # 切换到备用服务
            if self.backup is None:
                logger.error("[LLM Fallback] 无备用服务，重新抛出异常")
                raise
            
            used_backup = True
        
        # 使用备用服务
        try:
            logger.info(f"[LLM Fallback] 调用备用服务 ({self.backup_name})...")
            backup_start = time.time()
            
            for chunk in self.backup.call_with_text_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                conversation_history=conversation_history
            ):
                yield chunk
            
            backup_elapsed = time.time() - backup_start
            self.stats["backup_success"] += 1
            logger.info(f"[LLM Fallback] 备用服务完成, 耗时: {backup_elapsed:.2f}s")
            
        except Exception as e:
            self.stats["backup_error"] += 1
            logger.error(f"[LLM Fallback] 备用服务也失败: {e}")
            raise
    
    async def call_with_text_stream_async(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        loop=None
    ) -> AsyncGenerator[str, None]:
        """
        异步流式调用（带超时备用）
        
        使用 run_in_executor 将同步生成器转换为异步
        
        Yields:
            文本片段
        """
        if loop is None:
            loop = asyncio.get_event_loop()
        
        import queue
        import threading
        
        chunk_queue = queue.Queue()
        
        def run_stream():
            try:
                for chunk in self.call_with_text_stream_sync(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    conversation_history=conversation_history
                ):
                    chunk_queue.put(("chunk", chunk))
                chunk_queue.put(("done", None))
            except Exception as e:
                chunk_queue.put(("error", str(e)))
        
        # 启动线程
        thread = threading.Thread(target=run_stream, daemon=True)
        thread.start()
        
        # 异步消费
        while True:
            try:
                msg_type, data = await loop.run_in_executor(
                    None, lambda: chunk_queue.get(timeout=60)
                )
                
                if msg_type == "done":
                    break
                elif msg_type == "error":
                    raise Exception(data)
                elif msg_type == "chunk":
                    yield data
                    
            except Exception as e:
                import queue as q
                if isinstance(e, q.Empty):
                    logger.warning("[LLM Fallback] 队列超时")
                    break
                raise
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = sum(self.stats.values())
        if total == 0:
            return {**self.stats, "backup_rate": 0.0}
        
        backup_calls = self.stats["backup_success"] + self.stats["backup_error"]
        return {
            **self.stats,
            "total_calls": total,
            "backup_rate": backup_calls / max(1, self.stats["primary_success"] + self.stats["primary_timeout"] + self.stats["primary_error"]),
        }


# ==========================================
# 工厂函数
# ==========================================

def create_llm_fallback_service(
    primary_provider: str = "openrouter",
    backup_provider: str = "qwen",
    timeout_seconds: float = 5.0
) -> LLMFallbackService:
    """
    创建带备用机制的 LLM 服务
    
    Args:
        primary_provider: 主服务提供商 (openrouter, qwen)
        backup_provider: 备用服务提供商 (openrouter, qwen)
        timeout_seconds: 主服务超时时间
        
    Returns:
        LLMFallbackService 实例
    """
    primary = None
    backup = None
    
    # 创建主服务
    if primary_provider == "openrouter":
        from services.openrouter_audio import create_openrouter_service
        primary = create_openrouter_service()
        primary_name = "OpenRouter GPT-4o"
    elif primary_provider == "qwen":
        from services.qwen_omni_audio import create_qwen_omni_service
        primary = create_qwen_omni_service()
        primary_name = "Qwen-Omni"
    else:
        raise ValueError(f"Unknown primary provider: {primary_provider}")
    
    # 创建备用服务
    if backup_provider:
        if backup_provider == "openrouter":
            from services.openrouter_audio import create_openrouter_service
            backup = create_openrouter_service()
            backup_name = "OpenRouter GPT-4o"
        elif backup_provider == "qwen":
            from services.qwen_omni_audio import create_qwen_omni_service
            backup = create_qwen_omni_service()
            backup_name = "Qwen-Omni"
        else:
            backup = None
            backup_name = "None"
    else:
        backup = None
        backup_name = "None"
    
    return LLMFallbackService(
        primary_service=primary,
        backup_service=backup,
        timeout_seconds=timeout_seconds,
        primary_name=primary_name,
        backup_name=backup_name
    )
