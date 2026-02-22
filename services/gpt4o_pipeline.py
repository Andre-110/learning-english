"""
GPT-4o 三段链路服务 - ASR → LLM → TTS (同步版本 + 取消标志)

替代 Qwen-Omni S2S 模式，使用分离式三段链路：
1. ASR: GPT-4o Transcribe (Whisper)
2. LLM: GPT-4o (对话生成)
3. TTS: GPT-4o-mini-TTS (语音合成)

支持取消标志：当用户继续说话时，可以取消正在进行的处理。

🆕 学习自 UserGenie 的优化策略：
- LLM 超时 + Fallback：5秒超时后切换备用服务
- TTS 超时 + 重试：5秒超时，最多重试3次
- 思考中提示：LLM 超过 3 秒未响应显示"AI正在思考..."
- 性能指标追踪：完整追踪 ASR→LLM→TTS 各阶段延迟
"""
import base64
import time
import threading
import re
import signal
from typing import Optional, List, Dict, Any, Generator, Callable, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from openai import OpenAI  # 同步客户端

from prompts.templates import (
    get_pipeline_system_prompt,
    get_pipeline_system_prompt_with_memory,  # 🆕 支持 Layer 2 会话摘要
    get_pipeline_user_prompt,
    get_pipeline_initial_prompt,
    get_pipeline_initial_prompt_with_content,
    get_content_injection_prompt,
)
from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("services.gpt4o_pipeline")
settings = Settings()


# ==========================================
# 取消标志类
# ==========================================

class CancellationToken:
    """
    取消标志 - 用于在用户继续说话时取消正在进行的处理
    
    使用方式：
        token = CancellationToken()
        
        # 在处理循环中检查
        for chunk in stream:
            if token.is_cancelled:
                logger.info("任务被取消")
                return
            # 处理 chunk...
        
        # 当用户继续说话时
        token.cancel()
    """
    
    def __init__(self):
        self._cancelled = threading.Event()
    
    @property
    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._cancelled.is_set()
    
    def cancel(self):
        """设置取消标志"""
        self._cancelled.set()
        logger.info("[CancellationToken] 任务已标记为取消")
    
    def reset(self):
        """重置取消标志（用于复用 token）"""
        self._cancelled.clear()


@dataclass
class PerformanceMetrics:
    """
    🆕 性能指标追踪 - 学习自 UserGenie
    
    完整追踪 ASR → 语义检测 → LLM → TTS 各阶段延迟
    """
    # 时间戳（Unix 秒）
    user_stop_speaking_time: float = 0  # 用户停止说话时间（后端收到 stop_audio）
    asr_start_time: float = 0  # ASR 开始时间（流式已在说话时开始）
    asr_end_time: float = 0  # ASR 完成时间（获取到完整转录）
    semantic_start_time: float = 0  # 🆕 语义完整性检测开始时间
    semantic_end_time: float = 0  # 🆕 语义完整性检测结束时间
    llm_start_time: float = 0  # LLM 开始时间
    llm_first_token_time: float = 0  # LLM 第一个 token 时间（TTFT）
    llm_end_time: float = 0  # LLM 完成时间
    tts_start_time: float = 0  # TTS 开始时间
    tts_first_chunk_time: float = 0  # TTS 第一个音频块时间
    tts_end_time: float = 0  # TTS 完成时间
    
    # 计算的延迟（毫秒）
    @property
    def asr_latency_ms(self) -> int:
        """ASR 延迟（流式 ASR 时为获取最终结果的等待时间）"""
        if self.asr_start_time and self.asr_end_time:
            return int((self.asr_end_time - self.asr_start_time) * 1000)
        return 0
    
    @property
    def semantic_latency_ms(self) -> int:
        """🆕 语义完整性检测延迟"""
        if self.semantic_start_time and self.semantic_end_time:
            return int((self.semantic_end_time - self.semantic_start_time) * 1000)
        return 0
    
    @property
    def llm_ttft_ms(self) -> int:
        """Time To First Token"""
        if self.llm_start_time and self.llm_first_token_time:
            return int((self.llm_first_token_time - self.llm_start_time) * 1000)
        return 0
    
    @property
    def llm_total_ms(self) -> int:
        if self.llm_start_time and self.llm_end_time:
            return int((self.llm_end_time - self.llm_start_time) * 1000)
        return 0
    
    @property
    def tts_first_chunk_ms(self) -> int:
        """Time To First Audio Chunk"""
        if self.tts_start_time and self.tts_first_chunk_time:
            return int((self.tts_first_chunk_time - self.tts_start_time) * 1000)
        return 0
    
    @property
    def tts_total_ms(self) -> int:
        if self.tts_start_time and self.tts_end_time:
            return int((self.tts_end_time - self.tts_start_time) * 1000)
        return 0
    
    @property
    def total_latency_ms(self) -> int:
        """从用户停止说话到 AI 开始发出语音（后端处理时间，不含网络）"""
        if self.user_stop_speaking_time and self.tts_first_chunk_time:
            return int((self.tts_first_chunk_time - self.user_stop_speaking_time) * 1000)
        return 0
    
    @property
    def processing_latency_ms(self) -> int:
        """🆕 纯处理延迟 = ASR等待 + 语义检测 + LLM TTFT + TTS首块"""
        return self.asr_latency_ms + self.semantic_latency_ms + self.llm_ttft_ms + self.tts_first_chunk_ms
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于发送到前端）"""
        return {
            "asr_latency_ms": self.asr_latency_ms,
            "semantic_latency_ms": self.semantic_latency_ms,  # 🆕
            "llm_ttft_ms": self.llm_ttft_ms,
            "llm_total_ms": self.llm_total_ms,
            "tts_first_chunk_ms": self.tts_first_chunk_ms,
            "tts_total_ms": self.tts_total_ms,
            "total_latency_ms": self.total_latency_ms,
            "processing_latency_ms": self.processing_latency_ms,  # 🆕
        }
    
    def log_summary(self):
        """日志输出性能摘要"""
        logger.info("=" * 60)
        logger.info("📊 [性能指标] Performance Metrics")
        logger.info("=" * 60)
        logger.info(f"⏱️  Total Latency: {self.total_latency_ms}ms (后端收到 → TTS首块)")
        logger.info(f"📊 Processing:    {self.processing_latency_ms}ms (各阶段累加)")
        logger.info("-" * 60)
        logger.info(f"🎤 ASR 等待       : {self.asr_latency_ms}ms")
        logger.info(f"🧠 语义检测       : {self.semantic_latency_ms}ms")  # 🆕
        logger.info(f"🤖 LLM TTFT       : {self.llm_ttft_ms}ms")
        logger.info(f"🤖 LLM Total      : {self.llm_total_ms}ms")
        logger.info(f"🔊 TTS First Chunk: {self.tts_first_chunk_ms}ms")
        logger.info(f"🔊 TTS Total      : {self.tts_total_ms}ms")
        logger.info("=" * 60)


# ==========================================
# 配置
# ==========================================

def _get_openai_config() -> Dict[str, str]:
    """获取 OpenAI 官方 API 配置（从环境变量读取）"""
    api_key = settings.openai_official_api_key or settings.openai_api_key
    if not api_key:
        raise ValueError("未配置 OpenAI API Key，请在 .env 中设置 OPENAI_OFFICIAL_API_KEY")
    return {
        "api_key": api_key,
        "base_url": settings.openai_official_base_url or "https://api.openai.com/v1"
    }


@dataclass
class PipelineConfig:
    """GPT-4o 三段链路配置"""
    
    # ASR 配置
    asr_provider: str = field(default_factory=lambda: getattr(settings, 'asr_provider', 'openai'))
    asr_model: str = field(default_factory=lambda: settings.asr_model or "gpt-4o-transcribe")
    
    # LLM 配置
    llm_model: str = field(default_factory=lambda: settings.pipeline_llm_model or "gpt-4o")
    llm_backup_model: str = field(default_factory=lambda: getattr(settings, 'pipeline_llm_backup_model', None) or "gpt-4o-mini")
    llm_temperature: float = field(default_factory=lambda: settings.pipeline_llm_temperature or 0.8)
    llm_max_tokens: int = field(default_factory=lambda: settings.pipeline_llm_max_tokens or 150)
    # 🆕 参考 UserGenie: 5s 超时（原 10s 太长）
    llm_timeout_seconds: float = field(default_factory=lambda: getattr(settings, 'pipeline_llm_timeout', 5.0))
    
    # 🆕 学习自 UserGenie 的超时和重试配置
    llm_thinking_threshold_seconds: float = 3.0  # LLM 超过此时间显示"思考中"
    tts_timeout_seconds: float = 5.0  # TTS 超时时间
    tts_max_retries: int = 3  # TTS 最大重试次数
    tts_retry_delay_ms: int = 100  # TTS 重试间隔
    
    # TTS 配置
    tts_provider: str = field(default_factory=lambda: getattr(settings, 'pipeline_tts_provider', 'openai'))
    tts_model: str = field(default_factory=lambda: settings.pipeline_tts_model or "gpt-4o-mini-tts")
    tts_voice: str = field(default_factory=lambda: settings.pipeline_tts_voice or "nova")
    tts_speed: float = field(default_factory=lambda: settings.pipeline_tts_speed or 0.95)
    tts_instructions: str = field(default_factory=lambda: getattr(settings, 'pipeline_tts_instructions', None) or
        "Speak in a warm, friendly, and encouraging tone like a patient English tutor. "
        "Use natural pauses, vary your intonation, and sound genuinely interested in the conversation. "
        "Avoid sounding robotic or monotone.")
    
    # MiniMax TTS 配置
    minimax_api_key: str = field(default_factory=lambda: getattr(settings, 'minimax_api_key', '') or '')
    minimax_tts_model: str = field(default_factory=lambda: getattr(settings, 'minimax_tts_model', 'speech-2.6-hd'))
    minimax_tts_voice: str = field(default_factory=lambda: getattr(settings, 'minimax_tts_voice', 'male-qn-jingying'))
    
    # 豆包 ASR 配置
    doubao_asr_app_key: str = field(default_factory=lambda: getattr(settings, 'doubao_asr_app_key', '') or '')
    doubao_asr_access_key: str = field(default_factory=lambda: getattr(settings, 'doubao_asr_access_key', '') or '')


class GPT4oPipeline:
    """
    GPT-4o 三段链路服务 (同步版本)
    
    流程：
    1. ASR: 音频 → 文本 (Whisper/GPT-4o-transcribe/豆包 bigmodel)
    2. LLM: 文本 → AI 回复 (GPT-4o)
    3. TTS: AI 回复 → 音频 (GPT-4o-mini-TTS/MiniMax)
    
    支持通过 CancellationToken 取消正在进行的处理。
    支持多种 ASR 和 TTS Provider。
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()

        openai_config = _get_openai_config()
        if not openai_config["api_key"]:
            raise ValueError("OPENAI_API_KEY not set in environment.")
        
        # 修正 ASR 模型名称（仅 OpenAI Provider）
        if self.config.asr_provider == "openai":
            if self.config.asr_model == "gpt-4o-transcribe" and "api.openai.com" in openai_config["base_url"]:
                logger.info("[GPT4oPipeline] 检测到官方 API，自动将 ASR 模型修正为 whisper-1")
                self.config.asr_model = "whisper-1"
        
        # 使用同步 OpenAI 客户端（用于 LLM 和 OpenAI ASR/TTS）
        # 添加超时设置防止卡住：连接 10s，读取 60s
        self.client = OpenAI(
            api_key=openai_config["api_key"],
            base_url=openai_config["base_url"],
            timeout=60.0,  # 总超时 60 秒
            max_retries=2  # 失败重试 2 次
        )
        
        # 初始化豆包 ASR（如果配置）
        self._doubao_asr = None
        if self.config.asr_provider == "doubao":
            try:
                from services.doubao_asr import DoubaoASR, DoubaoASRConfig
                doubao_config = DoubaoASRConfig(
                    app_key=self.config.doubao_asr_app_key,
                    access_key=self.config.doubao_asr_access_key
                )
                # 注意：豆包 ASR 是流式的，这里只是准备配置
                self._doubao_asr_config = doubao_config
                logger.info("[GPT4oPipeline] 豆包 ASR 已配置")
            except Exception as e:
                logger.warning(f"[GPT4oPipeline] 豆包 ASR 初始化失败，回退到 OpenAI: {e}")
                self.config.asr_provider = "openai"
        
        # 初始化 MiniMax TTS（如果配置）
        self._minimax_tts = None
        if self.config.tts_provider == "minimax":
            try:
                from services.minimax_tts import MiniMaxTTSService, MiniMaxTTSConfig
                minimax_config = MiniMaxTTSConfig(
                    api_key=self.config.minimax_api_key,
                    model=self.config.minimax_tts_model,
                    default_voice=self.config.minimax_tts_voice,
                    speed=self.config.tts_speed
                )
                self._minimax_tts = MiniMaxTTSService(minimax_config)
                logger.info(f"[GPT4oPipeline] MiniMax TTS 已初始化: voice={self.config.minimax_tts_voice}")
            except Exception as e:
                logger.warning(f"[GPT4oPipeline] MiniMax TTS 初始化失败，回退到 OpenAI: {e}")
                self.config.tts_provider = "openai"
        
        # 填充音缓存
        self._filler_cache: Dict[str, bytes] = {}
        self._filler_phrases = ["Hmm...", "Let me see...", "Okay...", "Right...", "Well..."]

        logger.info(f"GPT-4o Pipeline 初始化完成: ASR={self.config.asr_provider}/{self.config.asr_model}, LLM={self.config.llm_model}, TTS={self.config.tts_provider}/{self.config.tts_model}")

    # ==========================================
    # 语音风格设置
    # ==========================================

    def set_voice_style(self, style_id: str) -> bool:
        from config.voice_styles import get_voice_style
        style = get_voice_style(style_id)
        if style:
            self.config.tts_voice = style.voice
            self.config.tts_speed = style.speed
            self.config.tts_instructions = style.instructions
            logger.info(f"[Pipeline] 语音风格已设置为: {style.name_zh} ({style_id})")
            return True
        return False

    def get_current_voice_style(self) -> Dict[str, Any]:
        return {
            "voice": self.config.tts_voice,
            "speed": self.config.tts_speed,
            "has_instructions": bool(self.config.tts_instructions)
        }

    # ==========================================
    # 填充音
    # ==========================================

    def get_filler_audio(self) -> Optional[bytes]:
        import random
        phrase = random.choice(self._filler_phrases)
        
        if phrase in self._filler_cache:
            return self._filler_cache[phrase]
        
        try:
            audio = self.synthesize(phrase)
            self._filler_cache[phrase] = audio
            return audio
        except Exception as e:
            logger.warning(f"[Filler] 生成失败: {e}")
            return None

    def preload_fillers(self) -> None:
        logger.info("[Filler] 开始预加载填充音...")
        for phrase in self._filler_phrases:
            if phrase not in self._filler_cache:
                try:
                    audio = self.synthesize(phrase)
                    self._filler_cache[phrase] = audio
                except Exception as e:
                    logger.warning(f"[Filler] 预加载失败 {phrase}: {e}")
        logger.info(f"[Filler] 预加载完成，共 {len(self._filler_cache)} 个")

    # ==========================================
    # 1. ASR 模块 - 语音识别
    # ==========================================

    def transcribe(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: str = "en",
        prompt: Optional[str] = None
    ) -> str:
        """ASR: 音频 → 文本（支持多种 Provider）"""
        start_time = time.time()

        try:
            if self.config.asr_provider == "doubao":
                # 使用豆包 ASR（同步批量模式）
                transcription = self._transcribe_with_doubao(audio_data, audio_format, language)
            else:
                # 默认使用 OpenAI Whisper
                transcription = self._transcribe_with_openai(audio_data, audio_format, language, prompt)

            elapsed = time.time() - start_time
            logger.info(f"[ASR/{self.config.asr_provider}] 完成, 耗时: {elapsed:.2f}s, 文本: {transcription[:50]}...")
            return transcription

        except Exception as e:
            logger.error(f"[ASR/{self.config.asr_provider}] 失败: {e}")
            raise
    
    def _transcribe_with_openai(
        self,
        audio_data: bytes,
        audio_format: str,
        language: str,
        prompt: Optional[str] = None
    ) -> str:
        """使用 OpenAI Whisper 进行 ASR"""
        request_params = {
            "model": self.config.asr_model,
            "file": ("audio." + audio_format, audio_data, f"audio/{audio_format}"),
            "language": language,
        }
        if prompt:
            request_params["prompt"] = prompt

        response = self.client.audio.transcriptions.create(**request_params)
        return response.text.strip()
    
    def _transcribe_with_doubao(
        self,
        audio_data: bytes,
        audio_format: str,
        language: str
    ) -> str:
        """使用豆包 bigmodel 进行 ASR（同步批量模式）"""
        import asyncio
        from services.doubao_asr import DoubaoASR
        
        async def run_asr():
            asr = DoubaoASR(self._doubao_asr_config)
            result_text = ""
            
            async def on_transcript(text, is_final):
                nonlocal result_text
                if is_final:
                    result_text = text
            
            await asr.start_stream(on_transcript=on_transcript)
            
            # 分块发送音频（每块 3200 bytes = 100ms @16kHz）
            chunk_size = 3200
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i+chunk_size]
                await asr.send_audio(chunk)
                await asyncio.sleep(0.02)  # 模拟实时发送
            
            final_result = await asr.stop_stream()
            return final_result or result_text
        
        # 在新的事件循环中运行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(run_asr())
        finally:
            loop.close()

    # ==========================================
    # 2. LLM 模块 - 对话生成
    # ==========================================

    def chat(
        self,
        user_text: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        memory_context: str = "",  # 🆕 Layer 2 会话摘要上下文
        stream: bool = False,
        cancel_token: Optional[CancellationToken] = None,
        on_thinking_start: Optional[Callable[[], None]] = None,
        on_thinking_end: Optional[Callable[[], None]] = None,
        metrics: Optional['PerformanceMetrics'] = None
    ) -> Generator[str, None, None]:
        """
        LLM: 文本 → AI 回复
        
        Args:
            memory_context: 🆕 三层记忆上下文（由 ConversationMemory.get_context_for_llm() 生成）
            cancel_token: 取消标志，如果设置且被取消，会提前终止生成
            on_thinking_start: 🆕 LLM 超过阈值时间未响应时的回调（显示"思考中..."）
            on_thinking_end: 🆕 收到第一个 token 时的回调（隐藏"思考中..."）
            metrics: 🆕 性能指标追踪
        """
        start_time = time.time()
        if metrics:
            metrics.llm_start_time = start_time

        # 🆕 根据是否有 memory_context 选择不同的 system prompt
        if memory_context:
            system_prompt = get_pipeline_system_prompt_with_memory(user_profile, memory_context)
            logger.info(f"[LLM] 🧠 使用三层记忆架构, memory_context 长度: {len(memory_context)} 字符")
        else:
            system_prompt = get_pipeline_system_prompt(user_profile)
        messages = [{"role": "system", "content": system_prompt}]

        # 🔧 强制截断 conversation_history（防止上下文过长导致延迟）
        MAX_HISTORY_TURNS = 6  # 最多保留 6 轮对话（12 条消息）
        MAX_HISTORY_TOKENS = 800  # 最多 800 tokens
        if conversation_history:
            # 1. 先按轮数截断
            if len(conversation_history) > MAX_HISTORY_TURNS * 2:
                conversation_history = conversation_history[-(MAX_HISTORY_TURNS * 2):]
                logger.info(f"[LLM] ⚠️ 历史截断: 保留最近 {MAX_HISTORY_TURNS} 轮")
            
            # 2. 再按 token 数截断
            total_tokens = sum(len(str(m.get('content', ''))) // 4 for m in conversation_history)
            while total_tokens > MAX_HISTORY_TOKENS and len(conversation_history) > 2:
                removed = conversation_history.pop(0)
                total_tokens -= len(str(removed.get('content', ''))) // 4
            if total_tokens <= MAX_HISTORY_TOKENS:
                logger.info(f"[LLM] ✂️ Token 截断后: {len(conversation_history)} 条, ~{total_tokens} tokens")

        # 调试：记录对话历史
        history_len = len(conversation_history) if conversation_history else 0
        
        # 🆕 估算上下文 token 数（用于延迟分析）
        system_tokens = len(system_prompt) // 4  # 粗略估算：4 字符 ≈ 1 token
        history_tokens = sum(len(str(m.get('content', ''))) // 4 for m in (conversation_history or []))
        user_tokens = len(user_text) // 4
        estimated_total_tokens = system_tokens + history_tokens + user_tokens
        
        if conversation_history:
            preview = conversation_history[-3:]  # 最近3条
            preview_str = ", ".join([f"{m.get('role', 'unknown')}: {str(m.get('content', ''))[:50]}..." for m in preview])
            logger.info(f"[LLM] 对话历史: {history_len} 条, 预览: {preview_str}")
        else:
            logger.info(f"[LLM] 对话历史: 空")
        
        # 🆕 记录上下文 token 估算（用于分析 token 数 vs 延迟关系）
        logger.info(f"[LLM] 📊 上下文分析: history_len={history_len}, tokens≈{estimated_total_tokens} (system:{system_tokens}, history:{history_tokens}, user:{user_tokens})")

        user_prompt = get_pipeline_user_prompt(user_text, conversation_history)
        messages.append({"role": "user", "content": user_prompt})

        logger.info(f"[LLM] 请求: {len(messages)} 条消息, 用户输入: {user_text[:50]}...")

        # 🆕 备用机制：主模型失败时自动切换
        models_to_try = [self.config.llm_model]
        if self.config.llm_backup_model and self.config.llm_backup_model != self.config.llm_model:
            models_to_try.append(self.config.llm_backup_model)
        
        # 🆕 思考中提示状态
        thinking_timer = None
        thinking_shown = False
        
        def start_thinking_timer():
            nonlocal thinking_timer, thinking_shown
            def show_thinking():
                nonlocal thinking_shown
                if not thinking_shown and on_thinking_start:
                    thinking_shown = True
                    logger.info(f"[LLM] 超过 {self.config.llm_thinking_threshold_seconds}s 未响应，显示思考中...")
                    try:
                        on_thinking_start()
                    except Exception as e:
                        logger.warning(f"[LLM] on_thinking_start 回调失败: {e}")
            
            thinking_timer = threading.Timer(self.config.llm_thinking_threshold_seconds, show_thinking)
            thinking_timer.daemon = True
            thinking_timer.start()
        
        def cancel_thinking_timer():
            nonlocal thinking_timer, thinking_shown
            if thinking_timer:
                thinking_timer.cancel()
                thinking_timer = None
            if thinking_shown and on_thinking_end:
                try:
                    on_thinking_end()
                except Exception as e:
                    logger.warning(f"[LLM] on_thinking_end 回调失败: {e}")
        
        last_error = None
        for model_idx, current_model in enumerate(models_to_try):
            is_backup = model_idx > 0
            if is_backup:
                logger.warning(f"[LLM] 主模型失败，切换到备用模型: {current_model}")
                # 重置思考状态
                thinking_shown = False
            
            try:
                # 🆕 启动思考中提示定时器
                if on_thinking_start:
                    start_thinking_timer()
                
                if stream:
                    response = self.client.chat.completions.create(
                        model=current_model,
                        messages=messages,
                        temperature=self.config.llm_temperature,
                        max_tokens=self.config.llm_max_tokens,
                        stream=True,
                        timeout=self.config.llm_timeout_seconds
                    )

                    full_reply = ""
                    first_chunk = True

                    for chunk in response:
                        # 检查取消标志
                        if cancel_token and cancel_token.is_cancelled:
                            logger.info("[LLM] 任务被取消，停止生成")
                            cancel_thinking_timer()
                            return

                        if chunk.choices and chunk.choices[0].delta.content:
                            text = chunk.choices[0].delta.content
                            full_reply += text

                            if first_chunk:
                                ttft = time.time() - start_time
                                model_tag = "(备用)" if is_backup else ""
                                logger.info(f"[LLM] 首字延迟 (TTFT): {ttft:.2f}s {model_tag}")
                                first_chunk = False
                                
                                # 🆕 取消思考中提示
                                cancel_thinking_timer()
                                
                                # 🆕 记录 TTFT
                                if metrics:
                                    metrics.llm_first_token_time = time.time()

                            yield text

                    elapsed = time.time() - start_time
                    elapsed_ms = int(elapsed * 1000)
                    model_tag = "(备用)" if is_backup else ""
                    logger.info(f"[LLM] 流式完成{model_tag}, 总耗时: {elapsed:.2f}s, 回复: {full_reply[:50]}...")
                    
                    # 🆕 延迟分析日志（用于分析 token 数 vs 延迟关系）
                    logger.info(f"[LLM] ⏱️ 延迟分析: history_len={history_len}, tokens≈{estimated_total_tokens}, latency={elapsed_ms}ms")
                    
                    # 🆕 记录完成时间
                    if metrics:
                        metrics.llm_end_time = time.time()
                    
                    return  # 成功，退出循环
                else:
                    response = self.client.chat.completions.create(
                        model=current_model,
                        messages=messages,
                        temperature=self.config.llm_temperature,
                        max_tokens=self.config.llm_max_tokens,
                        timeout=self.config.llm_timeout_seconds
                    )
                    
                    # 🆕 取消思考中提示
                    cancel_thinking_timer()
                    
                    reply = response.choices[0].message.content.strip()
                    elapsed = time.time() - start_time
                    model_tag = "(备用)" if is_backup else ""
                    logger.info(f"[LLM] 完成{model_tag}, 耗时: {elapsed:.2f}s, 回复: {reply[:50]}...")
                    
                    # 🆕 记录时间
                    if metrics:
                        metrics.llm_first_token_time = time.time()
                        metrics.llm_end_time = time.time()
                    
                    yield reply
                    return  # 成功，退出循环

            except Exception as e:
                last_error = e
                cancel_thinking_timer()
                logger.error(f"[LLM] 模型 {current_model} 失败: {e}")
                if model_idx < len(models_to_try) - 1:
                    continue  # 尝试下一个模型
                else:
                    raise  # 所有模型都失败，抛出异常

    # ==========================================
    # 3. TTS 模块 - 语音合成
    # ==========================================

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        instructions: Optional[str] = None
    ) -> bytes:
        """
        TTS: 文本 → 音频（支持多种 Provider）
        
        🆕 学习自 UserGenie 的优化：
        - 超时控制：5秒超时
        - 自动重试：最多重试3次
        """
        start_time = time.time()

        if text in self._filler_cache:
            return self._filler_cache[text]

        # 🆕 超时和重试机制
        last_error = None
        for attempt in range(1, self.config.tts_max_retries + 1):
            try:
                if self.config.tts_provider == "minimax" and self._minimax_tts:
                    # 使用 MiniMax TTS（带超时）
                    audio_content = self._synthesize_with_minimax_timeout(text, voice, speed)
                else:
                    # 默认使用 OpenAI TTS（带超时）
                    audio_content = self._synthesize_with_openai_timeout(text, voice, speed, instructions)

                elapsed = time.time() - start_time
                if attempt > 1:
                    logger.info(f"[TTS/{self.config.tts_provider}] 第{attempt}次尝试成功, 耗时: {elapsed:.2f}s")
                else:
                    logger.info(f"[TTS/{self.config.tts_provider}] 完成, 耗时: {elapsed:.2f}s, 音频大小: {len(audio_content)} bytes")

                if text in self._filler_phrases:
                    self._filler_cache[text] = audio_content

                return audio_content

            except Exception as e:
                last_error = e
                is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower()
                error_type = "超时" if is_timeout else "失败"
                logger.warning(f"[TTS Retry] 第{attempt}/{self.config.tts_max_retries}次{error_type}: {e}")
                
                if attempt < self.config.tts_max_retries:
                    time.sleep(self.config.tts_retry_delay_ms / 1000.0)
        
        # 所有重试都失败
        logger.error(f"[TTS/{self.config.tts_provider}] 所有{self.config.tts_max_retries}次尝试都失败")
        raise last_error or Exception("TTS failed after all retries")
    
    def _synthesize_with_openai_timeout(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        instructions: Optional[str] = None
    ) -> bytes:
        """使用 OpenAI TTS 进行语音合成（带超时）"""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        
        def do_tts():
            return self._synthesize_with_openai(text, voice, speed, instructions)
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(do_tts)
            try:
                return future.result(timeout=self.config.tts_timeout_seconds)
            except TimeoutError:
                raise Exception(f"OpenAI TTS timeout ({self.config.tts_timeout_seconds}s)")
    
    def _synthesize_with_minimax_timeout(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None
    ) -> bytes:
        """使用 MiniMax TTS 进行语音合成（带超时）"""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        
        def do_tts():
            return self._synthesize_with_minimax(text, voice, speed)
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(do_tts)
            try:
                return future.result(timeout=self.config.tts_timeout_seconds)
            except TimeoutError:
                raise Exception(f"MiniMax TTS timeout ({self.config.tts_timeout_seconds}s)")
    
    def _synthesize_with_openai(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        instructions: Optional[str] = None
    ) -> bytes:
        """使用 OpenAI TTS 进行语音合成"""
        voice = voice or self.config.tts_voice
        speed = speed or self.config.tts_speed
        instructions = instructions or self.config.tts_instructions

        request_params = {
            "model": self.config.tts_model,
            "voice": voice,
            "input": text,
            "speed": speed,
            "response_format": "pcm"
        }
        if instructions:
            request_params["instructions"] = instructions

        response = self.client.audio.speech.create(**request_params)
        return response.content
    
    def _synthesize_with_minimax(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None
    ) -> bytes:
        """使用 MiniMax TTS 进行语音合成"""
        import asyncio
        
        voice = voice or self.config.minimax_tts_voice
        speed_str = str(speed) if speed else None
        
        async def run_tts():
            return await self._minimax_tts._text_to_speech_async(
                text=text,
                voice=voice,
                rate=speed_str
            )
        
        # 在新的事件循环中运行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(run_tts())
        finally:
            loop.close()
    
    def get_tts_sample_rate(self) -> int:
        """获取当前 TTS 的输出采样率"""
        if self.config.tts_provider == "minimax":
            return 32000  # MiniMax 输出 32kHz
        else:
            return 24000  # OpenAI TTS 输出 24kHz

    async def synthesize_stream_async(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None
    ):
        """
        🚀 流式 TTS：边生成边 yield 音频块
        
        参考 UserGenie 优化策略：
        - 前端更早开始播放（首块延迟 ~500ms vs 完整等待 3s）
        - 带超时重试机制
        - 🆕 文字同步 (textDelta)：每个音频块携带对应的文字片段
        
        Yields:
            dict: {
                "type": "audio_chunk",
                "data": str,           # base64 编码的 PCM 数据
                "format": "pcm",
                "sample_rate": int,
                "chunk_index": int,
                "is_first": bool,
                "is_last": bool,
                "text_delta": str,     # 🆕 对应的文字片段
            }
        """
        # 🆕 文字同步：预先计算文字分段
        is_chinese = bool(re.search(r'[\u4e00-\u9fa5]', text))
        if is_chinese:
            text_segments = list(text)  # 中文按字符分割
        else:
            text_segments = text.split()  # 英文按单词分割
        
        if self.config.tts_provider == "minimax" and self._minimax_tts:
            voice = voice or self.config.minimax_tts_voice
            speed = speed or self.config.tts_speed
            sample_rate = 32000  # MiniMax 输出 32kHz
            
            # 收集所有块以计算总数（用于文字分配）
            chunks_buffer = []
            async for chunk in self._minimax_tts.synthesize_stream_async(
                text=text,
                voice=voice,
                speed=speed
            ):
                chunks_buffer.append(chunk)
            
            # 计算每块对应的文字
            total_chunks = len(chunks_buffer)
            if total_chunks > 0:
                segments_per_chunk = max(1, len(text_segments) // total_chunks)
                text_offset = 0
                
                for i, chunk in enumerate(chunks_buffer):
                    # 计算这个块对应的文字
                    is_last = chunk["is_last"]
                    if is_last:
                        # 最后一块包含剩余所有文字
                        text_delta = ' '.join(text_segments[text_offset:]) if not is_chinese else ''.join(text_segments[text_offset:])
                    else:
                        end_offset = min(text_offset + segments_per_chunk, len(text_segments))
                        text_delta = ' '.join(text_segments[text_offset:end_offset]) if not is_chinese else ''.join(text_segments[text_offset:end_offset])
                        text_offset = end_offset
                    
                    yield {
                        "type": "audio_chunk",
                        "data": base64.b64encode(chunk["audio_bytes"]).decode("utf-8"),
                        "format": "pcm",
                        "sample_rate": sample_rate,
                        "chunk_index": chunk["chunk_index"],
                        "is_first": chunk["is_first"],
                        "is_last": chunk["is_last"],
                        "text_delta": text_delta,  # 🆕 文字同步
                    }
        else:
            # OpenAI TTS 不支持流式，回退到一次性生成
            logger.warning("[TTS Stream] OpenAI TTS 不支持流式，使用非流式模式")
            audio = self.synthesize(text, voice, speed)
            sample_rate = 24000
            
            # 分块发送（模拟流式）
            chunk_size = 4800 * 2  # 200ms @ 24kHz, 16-bit
            total_chunks = max(1, (len(audio) + chunk_size - 1) // chunk_size)
            segments_per_chunk = max(1, len(text_segments) // total_chunks)
            text_offset = 0
            
            for i in range(0, len(audio), chunk_size):
                chunk_data = audio[i:i+chunk_size]
                chunk_index = i // chunk_size
                is_last = chunk_index == total_chunks - 1
                
                # 计算文字片段
                if is_last:
                    text_delta = ' '.join(text_segments[text_offset:]) if not is_chinese else ''.join(text_segments[text_offset:])
                else:
                    end_offset = min(text_offset + segments_per_chunk, len(text_segments))
                    text_delta = ' '.join(text_segments[text_offset:end_offset]) if not is_chinese else ''.join(text_segments[text_offset:end_offset])
                    text_offset = end_offset
                
                yield {
                    "type": "audio_chunk",
                    "data": base64.b64encode(chunk_data).decode("utf-8"),
                    "format": "pcm",
                    "sample_rate": sample_rate,
                    "chunk_index": chunk_index,
                    "is_first": chunk_index == 0,
                    "is_last": is_last,
                    "text_delta": text_delta,  # 🆕 文字同步
                }
    
    def synthesize_stream(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        🚀 同步版流式 TTS（用于线程中调用）
        
        在新的事件循环中运行异步流式 TTS，边收边 yield 音频块。
        
        Yields:
            dict: 音频块信息
        """
        import asyncio
        import queue
        import threading
        
        if self.config.tts_provider != "minimax" or not self._minimax_tts:
            # 非 MiniMax，使用普通同步 TTS（带文字同步）
            audio = self.synthesize(text, voice, speed)
            sample_rate = self.get_tts_sample_rate()
            chunk_size = 4800 * 2  # 200ms
            total_chunks = max(1, (len(audio) + chunk_size - 1) // chunk_size)
            
            # 文字分段
            is_chinese = bool(re.search(r'[\u4e00-\u9fa5]', text))
            text_segments = list(text) if is_chinese else text.split()
            segments_per_chunk = max(1, len(text_segments) // total_chunks)
            text_offset = 0
            
            for i in range(0, len(audio), chunk_size):
                chunk_data = audio[i:i+chunk_size]
                chunk_index = i // chunk_size
                is_last = chunk_index == total_chunks - 1
                
                # 计算文字片段
                if is_last:
                    text_delta = ''.join(text_segments[text_offset:]) if is_chinese else ' '.join(text_segments[text_offset:])
                else:
                    end_offset = min(text_offset + segments_per_chunk, len(text_segments))
                    text_delta = ''.join(text_segments[text_offset:end_offset]) if is_chinese else ' '.join(text_segments[text_offset:end_offset])
                    text_offset = end_offset
                
                yield {
                    "type": "audio_chunk",
                    "data": base64.b64encode(chunk_data).decode("utf-8"),
                    "format": "pcm",
                    "sample_rate": sample_rate,
                    "chunk_index": chunk_index,
                    "is_first": chunk_index == 0,
                    "is_last": is_last,
                    "text_delta": text_delta,  # 🆕 文字同步
                }
            return
        
        # MiniMax 流式 TTS
        result_queue = queue.Queue()
        
        def run_async_tts():
            """在新线程中运行异步 TTS"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def collect_chunks():
                    try:
                        async for chunk in self.synthesize_stream_async(text, voice, speed):
                            result_queue.put(("chunk", chunk))
                        result_queue.put(("done", None))
                    except Exception as e:
                        result_queue.put(("error", e))
                
                loop.run_until_complete(collect_chunks())
            finally:
                loop.close()
        
        # 启动异步 TTS 线程
        tts_thread = threading.Thread(target=run_async_tts, daemon=True)
        tts_thread.start()
        
        # 边收边 yield
        while True:
            try:
                msg_type, data = result_queue.get(timeout=10.0)
                if msg_type == "chunk":
                    yield data
                elif msg_type == "done":
                    break
                elif msg_type == "error":
                    logger.error(f"[TTS Stream Sync] 错误: {data}")
                    raise data
            except queue.Empty:
                logger.warning("[TTS Stream Sync] 超时")
                break
        
        tts_thread.join(timeout=1.0)

    # ==========================================
    # 4. 文本链路 - LLM → TTS（跳过 ASR）
    # ==========================================

    def process_text(
        self,
        user_text: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        memory_context: str = "",  # 🆕 Layer 2 会话摘要上下文
        cancel_token: Optional[CancellationToken] = None,
        on_thinking_start: Optional[Callable[[], None]] = None,
        on_thinking_end: Optional[Callable[[], None]] = None,
        metrics: Optional['PerformanceMetrics'] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        文本链路处理：LLM → TTS（跳过 ASR）
        
        Args:
            memory_context: 🆕 三层记忆上下文（由 ConversationMemory.get_context_for_llm() 生成）
            cancel_token: 取消标志，当用户继续说话时可以取消处理
            on_thinking_start: 🆕 LLM 超时时显示"思考中..."
            on_thinking_end: 🆕 收到第一个 token 时隐藏"思考中..."
            metrics: 🆕 性能指标追踪
        
        Yields:
            - {"type": "text_chunk", "text": "..."}
            - {"type": "audio_chunk", "data": "base64", "format": "pcm"}
            - {"type": "audio_end"}
            - {"type": "thinking_indicator"}  # 🆕 LLM 超时时发送
            - {"type": "thinking_indicator_end"}  # 🆕 收到第一个 token 时发送
            - {"type": "cancelled"}  # 如果被取消
            - {"type": "done", "response": "...", "latency": {...}, "metrics": {...}}
        """
        total_start = time.time()
        if metrics:
            metrics.user_stop_speaking_time = total_start
        timings = {}

        if not user_text or user_text.strip() == "":
            logger.warning("[Pipeline] 输入文本为空，跳过处理")
            yield {"type": "done", "latency": {"total": 0}}
            return

        # Backchanneling: 立即发送填充音，降低用户感知延迟
        try:
            filler = self.get_filler_audio()
            if filler:
                import base64 as _b64
                sample_rate = self.get_tts_sample_rate()
                yield {"type": "filler_audio", "data": _b64.b64encode(filler).decode("utf-8"), "format": "pcm", "sample_rate": sample_rate}
        except Exception as _fe:
            logger.warning(f"[Filler] 发送填充音失败: {_fe}")

        llm_start = time.time()
        full_response = ""
        sentence_buffer = ""
        first_audio_sent = False
        tts_total_time = 0
        
        # 🆕 学习自 UserGenie: 追踪 TTFT（Time To First Token）
        first_text_chunk_received = False
        ttft_time = 0
        
        # 🆕 思考中提示状态
        thinking_shown = False
        
        def handle_thinking_start():
            nonlocal thinking_shown
            thinking_shown = True
            
        def handle_thinking_end():
            nonlocal thinking_shown
            if thinking_shown:
                thinking_shown = False

        try:
            for text_chunk in self.chat(
                user_text=user_text,
                conversation_history=conversation_history,
                user_profile=user_profile,
                memory_context=memory_context,  # 🆕 传递 Layer 2 会话摘要
                stream=True,
                cancel_token=cancel_token,
                on_thinking_start=on_thinking_start or handle_thinking_start,
                on_thinking_end=on_thinking_end or handle_thinking_end,
                metrics=metrics
            ):
                # 检查取消标志
                if cancel_token and cancel_token.is_cancelled:
                    logger.info("[Pipeline] 任务被取消，停止处理")
                    yield {"type": "cancelled", "partial_response": full_response}
                    return

                # 🆕 记录 TTFT
                if not first_text_chunk_received:
                    ttft_time = time.time() - llm_start
                    first_text_chunk_received = True

                full_response += text_chunk
                sentence_buffer += text_chunk
                yield {"type": "text_chunk", "text": text_chunk}

                # 分句逻辑
                while True:
                    sentence = None

                    # 首句激进触发
                    if not first_audio_sent and len(sentence_buffer) > 25:
                        for i, char in enumerate(sentence_buffer):
                            if char in '.?!,;' and i >= 20:
                                sentence = sentence_buffer[:i + 1].strip()
                                sentence_buffer = sentence_buffer[i + 1:].lstrip()
                                break

                    # 句末标点
                    if not sentence:
                        for i, char in enumerate(sentence_buffer):
                            if char in '.?!':
                                before = sentence_buffer[:i].strip()
                                if before.isdigit():
                                    continue
                                if len(before) >= 8:
                                    sentence = sentence_buffer[:i + 1].strip()
                                    sentence_buffer = sentence_buffer[i + 1:].lstrip()
                                    break

                    # 过长强制切分
                    if not sentence and len(sentence_buffer) > 80:
                        for i, char in enumerate(sentence_buffer):
                            if char in ',;:' and i >= 30:
                                sentence = sentence_buffer[:i + 1].strip()
                                sentence_buffer = sentence_buffer[i + 1:].lstrip()
                                break

                    if not sentence:
                        break

                    # 再次检查取消标志
                    if cancel_token and cancel_token.is_cancelled:
                        logger.info("[Pipeline] TTS 前检测到取消")
                        yield {"type": "cancelled", "partial_response": full_response}
                        return

                    # 🚀 流式 TTS 合成（边生成边发送，降低首音延迟）
                    if sentence:
                        if metrics and not metrics.tts_start_time:
                            metrics.tts_start_time = time.time()
                            yield {
                                "type": "tts_start",
                                "timestamp_ms": int(metrics.tts_start_time * 1000)
                            }
                        
                        tts_start = time.time()
                        try:
                            # 使用流式 TTS，边收边 yield
                            for audio_chunk in self.synthesize_stream(sentence):
                                if not first_audio_sent:
                                    first_audio_sent = True
                                    first_chunk_delay = (time.time() - tts_start) * 1000
                                    logger.info(f"[TTS Stream] 首块延迟: {first_chunk_delay:.0f}ms")
                                    if metrics:
                                        metrics.tts_first_chunk_time = time.time()
                                yield audio_chunk
                            
                            tts_total_time += time.time() - tts_start
                        except Exception as e:
                            logger.error(f"[TTS Stream] 句子合成失败: {e}")

            # 处理剩余文本（流式 TTS）
            if sentence_buffer.strip():
                if cancel_token and cancel_token.is_cancelled:
                    yield {"type": "cancelled", "partial_response": full_response}
                    return

                if metrics and not metrics.tts_start_time:
                    metrics.tts_start_time = time.time()
                    yield {
                        "type": "tts_start",
                        "timestamp_ms": int(metrics.tts_start_time * 1000)
                    }
                
                tts_start = time.time()
                try:
                    for audio_chunk in self.synthesize_stream(sentence_buffer.strip()):
                        if not first_audio_sent:
                            first_audio_sent = True
                            if metrics:
                                metrics.tts_first_chunk_time = time.time()
                        yield audio_chunk
                    tts_total_time += time.time() - tts_start
                except Exception as e:
                    logger.error(f"[TTS Stream] 剩余文本合成失败: {e}")

            if metrics:
                metrics.tts_end_time = time.time()

            timings["llm"] = time.time() - llm_start - tts_total_time
            timings["tts"] = tts_total_time
            timings["ttft"] = ttft_time  # 🆕 TTFT
            yield {"type": "audio_end"}

        except Exception as e:
            logger.error(f"[Pipeline] LLM+TTS 失败: {e}")
            yield {"type": "error", "message": f"处理失败: {e}"}
            return

        timings["total"] = time.time() - total_start
        
        # 🆕 增强日志：包含完整性能指标
        if metrics:
            metrics.log_summary()
        else:
            logger.info(f"[Pipeline-Text] TTFT: {timings.get('ttft', 0)*1000:.0f}ms, LLM: {timings['llm']*1000:.0f}ms, TTS: {timings['tts']*1000:.0f}ms, Total: {timings['total']*1000:.0f}ms")

        yield {
            "type": "done",
            "response": full_response,
            "latency": {
                "ttft_ms": round(timings.get("ttft", 0) * 1000),  # 🆕 TTFT
                "llm_ms": round(timings["llm"] * 1000),
                "tts_ms": round(timings["tts"] * 1000),
                "total_ms": round(timings["total"] * 1000),
            },
            "metrics": metrics.to_dict() if metrics else None  # 🆕 完整性能指标
        }

    # ==========================================
    # 5. 生成初始问题
    # ==========================================

    def generate_initial_question(
        self,
        user_profile: Optional[Dict[str, Any]] = None,
        last_summary: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """生成初始问候语 - 支持朋友式个性化开场"""
        start_time = time.time()
        prompt = get_pipeline_initial_prompt(user_profile, last_summary)

        messages = [
            {"role": "system", "content": "Generate a friendly greeting. Output ONLY the greeting text."},
            {"role": "user", "content": prompt}
        ]

        full_text = ""

        try:
            response = self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=messages,
                temperature=0.9,
                max_tokens=100,
                stream=True
            )

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_text += text
                    yield {"type": "text_chunk", "text": text}

            # TTS
            audio = self.synthesize(full_text)
            chunk_size = 4096
            sample_rate = self.get_tts_sample_rate()
            for i in range(0, len(audio), chunk_size):
                yield {
                    "type": "audio_chunk",
                    "data": base64.b64encode(audio[i:i+chunk_size]).decode("utf-8"),
                    "format": "pcm",
                    "sample_rate": sample_rate
                }

            yield {"type": "audio_end"}

            elapsed = time.time() - start_time
            logger.info(f"[InitialQ] 完成, 耗时: {elapsed:.2f}s")

            yield {
                "type": "done",
                "text": full_text,
                "latency": {"total": round(elapsed, 2)}
            }

        except Exception as e:
            logger.error(f"[InitialQ] 失败: {e}")
            yield {"type": "error", "message": str(e)}

    # ==========================================
    # 5.5 生成结合热点的初始问题
    # ==========================================

    def generate_initial_question_with_content(
        self,
        user_profile: Optional[Dict[str, Any]] = None,
        hot_content: Optional[Dict[str, Any]] = None,
        last_summary: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """生成结合热点内容的初始问候语 - 支持朋友式个性化开场"""
        start_time = time.time()

        if hot_content and hot_content.get("detail"):
            prompt = get_pipeline_initial_prompt_with_content(user_profile, hot_content)
            has_hot_content = True
        else:
            # 🆕 传递 last_summary 用于朋友式开场
            prompt = get_pipeline_initial_prompt(user_profile, last_summary)
            has_hot_content = False

        messages = [
            {"role": "system", "content": "Generate a friendly greeting. Output ONLY the greeting text."},
            {"role": "user", "content": prompt}
        ]

        full_text = ""

        try:
            response = self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=messages,
                temperature=0.9,
                max_tokens=150 if has_hot_content else 100,
                stream=True
            )

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_text += text
                    yield {"type": "text_chunk", "text": text}

            audio = self.synthesize(full_text)
            chunk_size = 4096
            sample_rate = self.get_tts_sample_rate()
            for i in range(0, len(audio), chunk_size):
                yield {
                    "type": "audio_chunk",
                    "data": base64.b64encode(audio[i:i+chunk_size]).decode("utf-8"),
                    "format": "pcm",
                    "sample_rate": sample_rate
                }

            yield {"type": "audio_end"}

            elapsed = time.time() - start_time
            yield {
                "type": "done",
                "text": full_text,
                "has_hot_content": has_hot_content,
                "latency": {"total": round(elapsed, 2)}
            }

        except Exception as e:
            logger.error(f"[InitialQ+Content] 失败: {e}")
            yield {"type": "error", "message": str(e)}

    # ==========================================
    # 5.6 生成内容注入的回复
    # ==========================================

    def generate_response_with_content(
        self,
        user_text: str,
        hot_content: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        cancel_token: Optional[CancellationToken] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """生成注入热点内容的回复"""
        start_time = time.time()

        cefr_level = user_profile.get('cefr_level', 'B1') if user_profile else 'B1'

        context = ""
        if conversation_history:
            recent = conversation_history[-4:]
            context = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')[:100]}" for m in recent])

        prompt = get_content_injection_prompt(hot_content, context, cefr_level)

        messages = [
            {"role": "system", "content": "You are a friendly English tutor. Output ONLY your response."},
            {"role": "user", "content": prompt}
        ]

        full_text = ""

        try:
            response = self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=messages,
                temperature=0.8,
                max_tokens=200,
                stream=True
            )

            for chunk in response:
                if cancel_token and cancel_token.is_cancelled:
                    yield {"type": "cancelled"}
                    return

                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_text += text
                    yield {"type": "text_chunk", "text": text}

            # 🚀 使用流式 TTS
            for audio_chunk in self.synthesize_stream(full_text):
                yield audio_chunk

            yield {"type": "audio_end"}

            elapsed = time.time() - start_time
            yield {
                "type": "done",
                "text": full_text,
                "latency": {"total": round(elapsed, 2)}
            }

        except Exception as e:
            logger.error(f"[Response+Content] 失败: {e}")
            yield {"type": "error", "message": str(e)}


# ==========================================
# 工厂函数
# ==========================================

def create_gpt4o_pipeline(**kwargs) -> GPT4oPipeline:
    """创建 GPT-4o 三段链路实例"""
    config = PipelineConfig(**kwargs) if kwargs else None
    return GPT4oPipeline(config)
