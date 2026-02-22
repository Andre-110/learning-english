"""
评估轨 (Evaluation Track)

职责：三阶段评估（语音 + 文本 + 综合）
特点：异步执行，不阻塞交互轨

三阶段架构：
1. 语音评估 (Qwen-Omni): 发音 + 流利度
2. 文本评估 (GPT): 语法 + 词汇 + 句式
3. 综合评分 (GPT): 汇总 6 个维度

评分维度：
- 发音 (20%)
- 流利度 (15%)
- 语法 (25%)
- 词汇 (15%)
- 句式 (15%)
- 语义逻辑 (10%)
"""
import time
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from providers import create_llm_provider
from prompts.templates import (
    get_text_evaluation_system_prompt,
    get_text_evaluation_user_prompt,
    get_comprehensive_evaluation_system_prompt,
    get_comprehensive_evaluation_user_prompt,
)
from config.constants import (
    EVALUATION_STAGE_TIMEOUT,
    LLM_TEMPERATURE_EVALUATION,
    LLM_MAX_TOKENS_EVALUATION,
    CEFR_SCORE_RANGES,
    PROFILE_HISTORY_WEIGHT,
    PROFILE_CURRENT_WEIGHT,
)
from services.utils.logger import get_logger

logger = get_logger("tracks.evaluation")


@dataclass
class EvaluationResult:
    """评估结果"""
    transcription: str = ""
    overall_score: int = 50
    cefr_level: str = "A2"
    prosody_feedback: str = ""
    corrections: List[Dict[str, Any]] = field(default_factory=list)
    good_expressions: List[Dict[str, Any]] = field(default_factory=list)
    encouragement: str = "Keep practicing!"
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    score_breakdown: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transcription": self.transcription,
            "overall_score": self.overall_score,
            "cefr_level": self.cefr_level,
            "prosody_feedback": self.prosody_feedback,
            "corrections": self.corrections,
            "good_expressions": self.good_expressions,
            "encouragement": self.encouragement,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "interests": self.interests,
            "score_breakdown": self.score_breakdown,
        }


class EvaluationTrack:
    """
    评估轨 - 三阶段评估

    阶段1: 语音评估 (使用 Qwen-Omni 或 UnifiedProcessor)
    阶段2: 文本评估 (使用 GPT)
    阶段3: 综合评分 (使用 GPT)
    """

    def __init__(
        self,
        llm_provider=None,
        voice_evaluator=None  # 语音评估器（Qwen-Omni）
    ):
        """
        初始化评估轨

        Args:
            llm_provider: LLM 提供者（用于文本评估和综合评分）
            voice_evaluator: 语音评估器（用于阶段1）
        """
        self.llm = llm_provider or create_llm_provider()
        self.voice_evaluator = voice_evaluator  # 可以是 UnifiedProcessor

        logger.info("[评估轨] 初始化完成")

    async def evaluate(
        self,
        transcription: str,
        audio_data: Optional[bytes] = None,
        audio_format: str = "wav",
        user_profile: Optional[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """
        执行三阶段评估

        Args:
            transcription: 转录文本（来自交互轨 ASR）
            audio_data: 原始音频（用于语音评估）
            audio_format: 音频格式
            user_profile: 用户画像

        Returns:
            EvaluationResult
        """
        start_time = time.time()
        logger.info(f"[评估轨] 开始评估: {transcription[:50]}...")

        # 检查空输入
        if not transcription or transcription.strip() in ["", "[silence]", "[non-English]"]:
            logger.warning("[评估轨] 转录为空或无效，跳过")
            return EvaluationResult(transcription=transcription)

        loop = asyncio.get_event_loop()

        # ========== 阶段1 + 阶段2 并行 ==========
        voice_eval = {}
        text_eval = {}

        try:
            # 阶段1: 语音评估（如果有评估器和音频）
            async def run_voice_eval():
                if self.voice_evaluator and audio_data:
                    try:
                        result = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                lambda: self.voice_evaluator.evaluate_audio_no_context(
                                    audio_data=audio_data,
                                    audio_format=audio_format,
                                    user_profile=user_profile
                                )
                            ),
                            timeout=EVALUATION_STAGE_TIMEOUT
                        )
                        logger.info("[阶段1] 语音评估完成")
                        return result
                    except Exception as e:
                        logger.warning(f"[阶段1] 语音评估失败: {e}")
                return {}

            # 阶段2: 文本评估
            async def run_text_eval():
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self._evaluate_text(transcription)
                        ),
                        timeout=EVALUATION_STAGE_TIMEOUT
                    )
                    logger.info("[阶段2] 文本评估完成")
                    return result
                except Exception as e:
                    logger.warning(f"[阶段2] 文本评估失败: {e}")
                    return {}

            # 并行执行
            voice_eval, text_eval = await asyncio.gather(
                run_voice_eval(),
                run_text_eval()
            )

        except Exception as e:
            logger.error(f"[评估轨] 阶段1+2 失败: {e}")

        # ========== 阶段3: 综合评分 ==========
        try:
            final_result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self._evaluate_comprehensive(
                        transcription, voice_eval, text_eval
                    )
                ),
                timeout=EVALUATION_STAGE_TIMEOUT
            )
            logger.info("[阶段3] 综合评分完成")
        except Exception as e:
            logger.error(f"[阶段3] 综合评分失败: {e}")
            final_result = {}

        # ========== 构建结果 ==========
        # 🆕 应用短句惩罚（代码强制，确保评分合理）
        raw_score = final_result.get("overall_score", 50)
        adjusted_score = self._apply_word_count_cap(raw_score, transcription)
        
        # 🆕 interests 从阶段1（语音评估）获取，因为阶段3不输出 interests
        interests_from_voice = voice_eval.get("interests", []) if voice_eval else []
        
        result = EvaluationResult(
            transcription=transcription,
            overall_score=adjusted_score,
            cefr_level=self._score_to_cefr(adjusted_score),
            prosody_feedback=final_result.get("prosody_feedback", ""),
            corrections=final_result.get("corrections", []),
            good_expressions=final_result.get("good_expressions", []),
            encouragement=final_result.get("encouragement", "Keep practicing!"),
            strengths=final_result.get("strengths", []),
            weaknesses=final_result.get("weaknesses", []),
            interests=interests_from_voice,  # 🆕 从阶段1获取
            score_breakdown=final_result.get("score_breakdown", {}),
        )

        elapsed = time.time() - start_time
        logger.info(
            f"[评估轨] 完成: score={result.overall_score}, "
            f"level={result.cefr_level}, 耗时={elapsed:.2f}s"
        )

        return result

    def _evaluate_text(self, transcription: str) -> Dict[str, Any]:
        """
        阶段2: 文本评估（语法/词汇/句式）
        """
        import json

        system_prompt = get_text_evaluation_system_prompt()
        user_prompt = get_text_evaluation_user_prompt(transcription)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # 使用 JSON 模式
            from openai import OpenAI
            from config.settings import Settings
            settings = Settings()

            client = OpenAI(
                api_key=settings.openai_official_api_key or settings.openai_api_key,
                base_url=settings.openai_official_base_url
            )

            # 🔧 使用更快的模型进行评估（gpt-4o-mini 比 gpt-4o 快 3-5 倍）
            eval_model = "gpt-4o-mini"
            response = client.chat.completions.create(
                model=eval_model,
                messages=messages,
                temperature=LLM_TEMPERATURE_EVALUATION,
                max_tokens=LLM_MAX_TOKENS_EVALUATION,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content.strip()
            return json.loads(result_text)

        except Exception as e:
            logger.error(f"[文本评估] 失败: {e}")
            return {}

    def _evaluate_comprehensive(
        self,
        transcription: str,
        voice_eval: Dict[str, Any],
        text_eval: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        阶段3: 综合评分
        """
        import json

        system_prompt = get_comprehensive_evaluation_system_prompt()
        user_prompt = get_comprehensive_evaluation_user_prompt(
            transcription, voice_eval, text_eval
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            from openai import OpenAI
            from config.settings import Settings
            settings = Settings()

            client = OpenAI(
                api_key=settings.openai_official_api_key or settings.openai_api_key,
                base_url=settings.openai_official_base_url
            )

            # 🔧 使用更快的模型进行评估（gpt-4o-mini 比 gpt-4o 快 3-5 倍）
            eval_model = "gpt-4o-mini"
            response = client.chat.completions.create(
                model=eval_model,
                messages=messages,
                temperature=LLM_TEMPERATURE_EVALUATION,
                max_tokens=LLM_MAX_TOKENS_EVALUATION,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)

            # 确保必要字段
            if "overall_score" not in result:
                result["overall_score"] = 50
            if "transcription" not in result:
                result["transcription"] = transcription

            return result

        except Exception as e:
            logger.error(f"[综合评分] 失败: {e}")
            return {
                "transcription": transcription,
                "overall_score": 50,
                "cefr_level": "A2",
                "corrections": [],
                "good_expressions": [],
                "encouragement": "Keep practicing!",
            }

    def _apply_word_count_cap(self, score: int, transcription: str) -> int:
        """
        根据词数强制设置分数上限（短句惩罚）
        
        短句信息量不足，无法全面评估，应保守评分。
        """
        # 清理转录文本，计算实际词数
        # 只过滤填充词，不过滤 "like"（可能是动词）
        clean_text = transcription.strip().replace("...", " ").replace(".", " ")
        filler_words = {"um", "uh", "er", "ah", "hmm"}
        words = [w for w in clean_text.split() if w and w.lower() not in filler_words]
        word_count = len(words)
        
        # 短句分数上限
        caps = [
            (1, 2, 25),    # 1-2 词：最高 25 分
            (3, 4, 35),    # 3-4 词：最高 35 分
            (5, 6, 45),    # 5-6 词：最高 45 分
            (7, 8, 55),    # 7-8 词：最高 55 分
        ]
        
        for min_w, max_w, cap in caps:
            if min_w <= word_count <= max_w:
                if score > cap:
                    logger.info(
                        f"[评分校正] 短句惩罚: 词数={word_count}, "
                        f"原分={score} → 校正为={cap}"
                    )
                    return cap
        
        return score  # 9+ 词不限制

    def _score_to_cefr(self, score: int) -> str:
        """根据分数计算 CEFR 等级"""
        for level, (min_score, max_score) in CEFR_SCORE_RANGES.items():
            if min_score <= score < max_score:
                return level
        return "C2" if score >= 90 else "Pre-A1"

    @staticmethod
    def update_user_profile(
        profile: Dict[str, Any],
        result: EvaluationResult
    ) -> Dict[str, Any]:
        """
        根据评估结果更新用户画像

        使用加权平均，避免单轮波动：
        新分数 = 历史分数 * 0.7 + 本轮分数 * 0.3
        """
        # 加权平均计算分数
        old_score = profile.get("overall_score", 50.0)
        new_score = result.overall_score

        if old_score == 0 or profile.get("round_count", 0) == 0:
            weighted_score = new_score
        else:
            weighted_score = (
                old_score * PROFILE_HISTORY_WEIGHT +
                new_score * PROFILE_CURRENT_WEIGHT
            )

        profile["overall_score"] = round(weighted_score, 1)
        profile["cefr_level"] = EvaluationTrack._score_to_cefr_static(weighted_score)
        profile["round_count"] = profile.get("round_count", 0) + 1

        # 合并强项/弱项/兴趣
        for key in ["strengths", "weaknesses"]:
            new_items = getattr(result, key, [])
            existing = profile.get(key, [])
            profile[key] = list(dict.fromkeys(existing + new_items))[-5:]

        new_interests = result.interests or []
        existing_interests = profile.get("interests", [])
        profile["interests"] = list(dict.fromkeys(existing_interests + new_interests))[-10:]

        return profile

    @staticmethod
    def _score_to_cefr_static(score: float) -> str:
        """静态方法：分数转 CEFR"""
        for level, (min_score, max_score) in CEFR_SCORE_RANGES.items():
            if min_score <= score < max_score:
                return level
        return "C2" if score >= 90 else "Pre-A1"

