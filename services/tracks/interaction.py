"""
交互轨 (Interaction Track)

职责：ASR → LLM → TTS 三段链路
特点：流式输出，低延迟，分句并行 TTS

流程：
1. ASR: 用户音频 → 转录文本
2. LLM: 转录文本 + 历史 → AI 回复（流式）
3. TTS: AI 回复 → 音频（分句并行）
"""
import time
import base64
from typing import Optional, List, Dict, Any, Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from providers import create_asr_provider, create_llm_provider, create_tts_provider
from prompts.templates import get_pipeline_system_prompt, get_pipeline_user_prompt
from config.constants import (
    TTS_THREAD_POOL_SIZE,
    AUDIO_CHUNK_SIZE,
    SENTENCE_FIRST_TRIGGER_LENGTH,
    SENTENCE_MIN_LENGTH,
    SENTENCE_COMMA_TRIGGER_LENGTH,
    SENTENCE_FORCE_SPLIT_LENGTH,
)
from services.utils.logger import get_logger

logger = get_logger("tracks.interaction")


@dataclass
class InteractionResult:
    """交互轨结果"""
    transcription: str
    response: str
    latency: Dict[str, float]


class InteractionTrack:
    """
    交互轨 - ASR → LLM → TTS 三段链路

    使用 Provider 抽象，便于测试和切换实现。
    """

    def __init__(
        self,
        asr_provider=None,
        llm_provider=None,
        tts_provider=None
    ):
        """
        初始化交互轨

        Args:
            asr_provider: ASR 提供者，默认创建 OpenAI 实现
            llm_provider: LLM 提供者，默认创建 OpenAI 实现
            tts_provider: TTS 提供者，默认创建 OpenAI 实现
        """
        self.asr = asr_provider or create_asr_provider()
        self.llm = llm_provider or create_llm_provider()
        self.tts = tts_provider or create_tts_provider()

        logger.info("[交互轨] 初始化完成")

    def process(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        处理用户音频，返回 AI 回复

        流式输出：
        - {"type": "transcription", "text": "..."}  - 转录结果
        - {"type": "text_chunk", "text": "..."}     - LLM 文本块
        - {"type": "audio_chunk", "data": "base64"} - TTS 音频块
        - {"type": "audio_end"}                     - 音频结束
        - {"type": "done", "latency": {...}}        - 处理完成

        Args:
            audio_data: 用户音频数据
            audio_format: 音频格式
            conversation_history: 对话历史
            user_profile: 用户画像

        Yields:
            处理结果字典
        """
        total_start = time.time()
        timings = {}

        # ========== 1. ASR ==========
        asr_start = time.time()
        try:
            transcription = self.asr.transcribe(audio_data, audio_format)
            timings["asr"] = time.time() - asr_start

            yield {"type": "transcription", "text": transcription}

            if not transcription or transcription.strip() == "":
                logger.warning("[交互轨] 转录为空，跳过处理")
                yield {"type": "done", "latency": timings}
                return

        except Exception as e:
            logger.error(f"[交互轨] ASR 失败: {e}")
            yield {"type": "error", "message": f"ASR 失败: {e}"}
            return

        # ========== 2. LLM + TTS (流水线并行) ==========
        llm_start = time.time()
        full_response = ""
        tts_total_time = 0

        # 构建 LLM 消息
        system_prompt = get_pipeline_system_prompt(user_profile)
        user_prompt = get_pipeline_user_prompt(transcription, conversation_history)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # 并行 TTS
        tts_executor = ThreadPoolExecutor(max_workers=TTS_THREAD_POOL_SIZE)
        tts_futures = []
        audio_results = {}
        next_audio_index = 0
        sentence_buffer = ""
        sentence_index = 0
        first_audio_sent = False

        def tts_worker(sentence: str, idx: int) -> tuple:
            """TTS 工作线程"""
            start = time.time()
            try:
                audio = self.tts.synthesize(sentence, stream=False)
                elapsed = time.time() - start
                return (idx, audio, elapsed, None)
            except Exception as e:
                return (idx, None, 0, str(e))

        try:
            # 流式 LLM
            for text_chunk in self.llm.chat(messages, stream=True):
                full_response += text_chunk
                sentence_buffer += text_chunk

                # 发送文本块
                yield {"type": "text_chunk", "text": text_chunk}

                # 智能分句 + 提交 TTS
                while True:
                    sentence = self._extract_sentence(
                        sentence_buffer,
                        first_audio_sent
                    )
                    if not sentence:
                        break

                    sentence_buffer = sentence_buffer[len(sentence):].lstrip()

                    # 提交 TTS
                    future = tts_executor.submit(tts_worker, sentence.strip(), sentence_index)
                    tts_futures.append((sentence_index, future))
                    logger.debug(f"[交互轨] 提交 TTS #{sentence_index}: \"{sentence[:30]}...\"")
                    sentence_index += 1

                # 检查已完成的 TTS，按顺序发送
                for idx, future in list(tts_futures):
                    if future.done():
                        result_idx, audio_data_chunk, elapsed, error = future.result()
                        tts_futures.remove((idx, future))

                        if error:
                            logger.error(f"[交互轨] TTS #{result_idx} 失败: {error}")
                            continue

                        audio_results[result_idx] = audio_data_chunk
                        tts_total_time += elapsed

                        # 按顺序发送
                        while next_audio_index in audio_results:
                            audio = audio_results.pop(next_audio_index)

                            if not first_audio_sent:
                                ttfa = time.time() - llm_start
                                logger.info(f"[交互轨] 首音频延迟 (TTFA): {ttfa:.2f}s")
                                first_audio_sent = True

                            # 分块发送
                            for i in range(0, len(audio), AUDIO_CHUNK_SIZE):
                                yield {
                                    "type": "audio_chunk",
                                    "data": base64.b64encode(audio[i:i+AUDIO_CHUNK_SIZE]).decode("utf-8"),
                                    "format": "pcm"
                                }
                            next_audio_index += 1

            # 处理剩余文本
            if sentence_buffer.strip():
                future = tts_executor.submit(tts_worker, sentence_buffer.strip(), sentence_index)
                tts_futures.append((sentence_index, future))
                sentence_index += 1

            # 等待所有 TTS 完成
            for idx, future in tts_futures:
                result_idx, audio_data_chunk, elapsed, error = future.result()
                if error:
                    continue
                audio_results[result_idx] = audio_data_chunk
                tts_total_time += elapsed

            # 发送剩余音频
            while next_audio_index in audio_results:
                audio = audio_results.pop(next_audio_index)

                if not first_audio_sent:
                    first_audio_sent = True

                for i in range(0, len(audio), AUDIO_CHUNK_SIZE):
                    yield {
                        "type": "audio_chunk",
                        "data": base64.b64encode(audio[i:i+AUDIO_CHUNK_SIZE]).decode("utf-8"),
                        "format": "pcm"
                    }
                next_audio_index += 1

            timings["llm"] = time.time() - llm_start - tts_total_time
            timings["tts"] = tts_total_time

            yield {"type": "audio_end"}

        except Exception as e:
            logger.error(f"[交互轨] LLM+TTS 失败: {e}")
            yield {"type": "error", "message": f"处理失败: {e}"}
            return
        finally:
            tts_executor.shutdown(wait=False)

        # ========== 完成 ==========
        timings["total"] = time.time() - total_start

        logger.info(
            f"[交互轨] 完成: ASR={timings['asr']:.2f}s, "
            f"LLM={timings['llm']:.2f}s, TTS={timings['tts']:.2f}s, "
            f"Total={timings['total']:.2f}s"
        )

        yield {
            "type": "done",
            "transcription": transcription,
            "response": full_response,
            "latency": {
                "asr_ms": round(timings["asr"] * 1000),
                "llm_ms": round(timings["llm"] * 1000),
                "tts_ms": round(timings["tts"] * 1000),
                "total_ms": round(timings["total"] * 1000),
            }
        }

    def _extract_sentence(self, buffer: str, first_sent: bool) -> Optional[str]:
        """
        智能分句策略

        Args:
            buffer: 当前缓冲区
            first_sent: 是否已发送首句

        Returns:
            提取的句子，或 None
        """
        # 策略1: 首句激进触发
        if not first_sent and len(buffer) > SENTENCE_FIRST_TRIGGER_LENGTH:
            for i, char in enumerate(buffer):
                if char in '.?!,;' and i >= 20:
                    return buffer[:i + 1]

        # 策略2: 句末标点
        for i, char in enumerate(buffer):
            if char in '.?!':
                before = buffer[:i].strip()
                if before.isdigit():
                    continue
                if len(before) >= SENTENCE_MIN_LENGTH:
                    return buffer[:i + 1]

        # 策略3: 逗号分句（缓冲区较长时）
        if len(buffer) > SENTENCE_COMMA_TRIGGER_LENGTH:
            for i, char in enumerate(buffer):
                if char in ',;' and i >= 20:
                    return buffer[:i + 1]

        # 策略4: 强制分句
        if len(buffer) > SENTENCE_FORCE_SPLIT_LENGTH:
            last_space = buffer.rfind(' ', 40, 70)
            if last_space > 0:
                return buffer[:last_space]

        return None

    def generate_greeting(
        self,
        user_profile: Optional[Dict[str, Any]] = None,
        hot_content: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        生成开场白

        Args:
            user_profile: 用户画像
            hot_content: 热点内容（可选）

        Yields:
            - {"type": "text_chunk", "text": "..."}
            - {"type": "audio_chunk", "data": "base64"}
            - {"type": "audio_end"}
            - {"type": "done", "text": "..."}
        """
        from prompts.templates import (
            get_pipeline_initial_prompt,
            get_pipeline_initial_prompt_with_content
        )

        start_time = time.time()

        # 选择 prompt
        if hot_content and hot_content.get("detail"):
            prompt = get_pipeline_initial_prompt_with_content(user_profile, hot_content)
            has_hot_content = True
        else:
            prompt = get_pipeline_initial_prompt(user_profile)
            has_hot_content = False

        messages = [
            {"role": "system", "content": "Generate a friendly greeting. Output ONLY the greeting text."},
            {"role": "user", "content": prompt}
        ]

        full_text = ""

        try:
            # 流式 LLM
            for text_chunk in self.llm.chat(messages, temperature=0.9, max_tokens=100, stream=True):
                full_text += text_chunk
                yield {"type": "text_chunk", "text": text_chunk}

            # TTS
            for audio_chunk in self.tts.synthesize(full_text, stream=True):
                yield {
                    "type": "audio_chunk",
                    "data": base64.b64encode(audio_chunk).decode("utf-8"),
                    "format": "pcm"
                }

            yield {"type": "audio_end"}

            elapsed = time.time() - start_time
            logger.info(f"[交互轨] 开场白完成, 耗时: {elapsed:.2f}s")

            yield {
                "type": "done",
                "text": full_text,
                "has_hot_content": has_hot_content,
                "latency": {"total": round(elapsed, 2)}
            }

        except Exception as e:
            logger.error(f"[交互轨] 开场白失败: {e}")
            yield {"type": "error", "message": str(e)}

