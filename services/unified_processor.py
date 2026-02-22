"""
统一处理器 - 两套服务的共用入口

职责：
1. 从 prompts/templates.py 获取 prompt
2. 调用 API 服务（DashScope 或 OpenRouter）
3. 解析响应
4. 更新用户画像

支持的服务：
- DashScope: 阿里云 qwen-audio-turbo-latest（支持真正的流式输出）
- OpenRouter: GPT-4o Audio
"""
import json
import re
from typing import Optional, Dict, Any, List, Generator, Union
from dataclasses import dataclass, field

from prompts.templates import (
    get_system_prompt,
    get_user_prompt_for_audio,
    get_user_prompt_for_text,
    get_initial_question_prompt,
    # 四轨并行新接口
    get_interaction_system_prompt,
    get_transcription_system_prompt,
    get_transcription_user_prompt,
    get_evaluation_system_prompt,
    get_evaluation_user_prompt,
    get_translation_system_prompt,
    get_translation_user_prompt
)
from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("services.unified_processor")
settings = Settings()


@dataclass
class ProcessingResult:
    """统一的处理结果"""
    transcription: str = ""
    evaluation: Dict[str, Any] = field(default_factory=lambda: {
        "overall_score": 50,
        "cefr_level": "A2",
        "strengths": [],
        "weaknesses": [],
        "corrections": [],
        "good_expressions": [],
        "encouragement": ""
    })
    interests: List[str] = field(default_factory=list)
    ai_feedback: str = ""
    next_question: str = ""
    full_response: str = ""
    # 对话节奏标记（阶段 2 新增）
    rhythm_hints: Dict[str, Any] = field(default_factory=lambda: {
        "response_length": "normal",  # short / normal / long
        "should_switch_topic": False,
        "consecutive_short_count": 0,
        "suggested_strategy": "continue"  # continue / switch_topic / lighten / encourage
    })
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "transcription": self.transcription,
            "evaluation": self.evaluation,
            "interests": self.interests,
            "ai_feedback": self.ai_feedback,
            "next_question": self.next_question,
            "full_response": self.full_response,
            "rhythm_hints": self.rhythm_hints
        }


class ConversationRhythmAnalyzer:
    """
    对话节奏分析器（阶段 2 新增）
    
    分析用户回答，给出节奏建议：
    - 短答/重复答 → 换话题或轻引导
    - 中等长度 → 正常追问
    - 长答 → 总结+延展
    """
    
    # 短答阈值（词数）
    SHORT_ANSWER_THRESHOLD = 5
    # 长答阈值（词数）
    LONG_ANSWER_THRESHOLD = 20
    # 连续短答触发换话题的次数
    CONSECUTIVE_SHORT_TRIGGER = 2
    
    # 常见短答模式
    SHORT_ANSWER_PATTERNS = [
        r'^(yes|no|yeah|yep|nope|ok|okay|fine|good|sure|right|maybe|i think so|i don\'t know|idk)\.?$',
        r'^(好|是|不|对|行|嗯|哦|可以|不知道|没有)$',
    ]
    
    @staticmethod
    def analyze(
        transcription: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        分析用户回答，返回节奏建议
        
        Args:
            transcription: 当前用户转录
            conversation_history: 对话历史（用于检测连续短答）
            
        Returns:
            节奏提示字典
        """
        hints = {
            "response_length": "normal",
            "should_switch_topic": False,
            "consecutive_short_count": 0,
            "suggested_strategy": "continue"
        }
        
        if not transcription:
            hints["response_length"] = "short"
            hints["suggested_strategy"] = "encourage"
            return hints
        
        # 计算词数（简单分词）
        words = transcription.split()
        word_count = len(words)
        
        # 判断回答长度
        if word_count <= ConversationRhythmAnalyzer.SHORT_ANSWER_THRESHOLD:
            hints["response_length"] = "short"
        elif word_count >= ConversationRhythmAnalyzer.LONG_ANSWER_THRESHOLD:
            hints["response_length"] = "long"
        else:
            hints["response_length"] = "normal"
        
        # 检查是否匹配短答模式
        is_pattern_short = False
        for pattern in ConversationRhythmAnalyzer.SHORT_ANSWER_PATTERNS:
            if re.match(pattern, transcription.lower().strip(), re.IGNORECASE):
                is_pattern_short = True
                hints["response_length"] = "short"
                break
        
        # 统计连续短答次数
        consecutive_short = 0
        if conversation_history:
            # 从最近的用户消息往前数
            for msg in reversed(conversation_history):
                if msg.get('role') == 'user':
                    content = msg.get('content', '')
                    msg_words = len(content.split())
                    if msg_words <= ConversationRhythmAnalyzer.SHORT_ANSWER_THRESHOLD:
                        consecutive_short += 1
                    else:
                        break  # 遇到非短答就停止计数
        
        # 当前回答也是短答，计入
        if hints["response_length"] == "short":
            consecutive_short += 1
        
        hints["consecutive_short_count"] = consecutive_short
        
        # 根据分析结果给出策略建议
        if consecutive_short >= ConversationRhythmAnalyzer.CONSECUTIVE_SHORT_TRIGGER:
            hints["should_switch_topic"] = True
            hints["suggested_strategy"] = "switch_topic"
        elif hints["response_length"] == "short":
            hints["suggested_strategy"] = "lighten"  # 轻引导，给出选择
        elif hints["response_length"] == "long":
            hints["suggested_strategy"] = "summarize"  # 总结+延展
        else:
            hints["suggested_strategy"] = "continue"  # 正常继续
        
        return hints


class ResponseParser:
    """响应解析器"""
    
    @staticmethod
    def _fix_json_placeholders(json_str: str) -> str:
        """修复 JSON 中的占位符，如 0-100 -> 50"""
        # 替换 "overall_score": 0-100 为 "overall_score": 50
        json_str = re.sub(r'"overall_score":\s*0-100', '"overall_score": 50', json_str)
        # 替换 "cefr_level": "A1/A2/B1/B2/C1/C2" 为 "cefr_level": "A2"
        json_str = re.sub(r'"cefr_level":\s*"A1/A2/B1/B2/C1/C2"', '"cefr_level": "A2"', json_str)
        return json_str
    
    @staticmethod
    def _extract_response_text(response_text: str) -> str:
        """从原始文本中提取 response 字段的值"""
        # 尝试用正则直接提取 response 字段
        match = re.search(r'"response":\s*"([^"]*(?:\\"[^"]*)*)"', response_text)
        if match:
            return match.group(1).replace('\\"', '"')
        return ""
    
    @staticmethod
    def _extract_transcription(response_text: str) -> str:
        """从原始文本中提取 transcription 字段"""
        match = re.search(r'"transcription":\s*"([^"]*(?:\\"[^"]*)*)"', response_text)
        if match:
            return match.group(1).replace('\\"', '"')
        return ""
    
    @staticmethod
    def _extract_evaluation(response_text: str) -> dict:
        """从原始文本中提取评估信息"""
        eval_data = {
            "overall_score": 50,
            "cefr_level": "A2",
            "strengths": [],
            "weaknesses": [],
            "corrections": [],
            "good_expressions": [],
            "encouragement": ""
        }
        
        # 提取分数
        score_match = re.search(r'"overall_score":\s*(\d+)', response_text)
        if score_match:
            eval_data["overall_score"] = int(score_match.group(1))
        
        # 提取 CEFR 等级（支持 Pre-A1）
        level_match = re.search(r'"cefr_level":\s*"(Pre-A1|[A-C][12])"', response_text)
        if level_match:
            eval_data["cefr_level"] = level_match.group(1)
        
        # 提取鼓励语
        enc_match = re.search(r'"encouragement":\s*"([^"]*)"', response_text)
        if enc_match:
            eval_data["encouragement"] = enc_match.group(1)
        
        # 提取 corrections 数组
        try:
            corrections_match = re.search(r'"corrections":\s*\[(.*?)\]', response_text, re.DOTALL)
            if corrections_match:
                corrections_str = '[' + corrections_match.group(1) + ']'
                # 尝试解析 corrections 数组
                corrections = json.loads(corrections_str)
                if isinstance(corrections, list):
                    eval_data["corrections"] = corrections
        except (json.JSONDecodeError, Exception):
            pass
        
        # 提取 good_expressions 数组
        try:
            good_expr_match = re.search(r'"good_expressions":\s*\[(.*?)\]', response_text, re.DOTALL)
            if good_expr_match:
                good_expr_str = '[' + good_expr_match.group(1) + ']'
                good_expressions = json.loads(good_expr_str)
                if isinstance(good_expressions, list):
                    eval_data["good_expressions"] = good_expressions
        except (json.JSONDecodeError, Exception):
            pass
        
        return eval_data
    
    @staticmethod
    def is_sentence_complete(text: str) -> bool:
        """
        检查句子是否完整（用于防止 AI 打断用户）
        
        使用 TextPreprocessor 进行增强检查，支持：
        - 废词过滤
        - 意图切换检测
        - 更全面的未完成结尾词检测
        """
        from services.text_preprocessor import get_text_preprocessor
        
        preprocessor = get_text_preprocessor()
        is_complete, confidence = preprocessor.is_sentence_complete(text)
        
        # 只有高置信度才认为完整
        return is_complete and confidence >= 0.5
    
    @staticmethod
    def preprocess_text(text: str):
        """
        预处理转录文本
        
        返回预处理结果，包含：
        - cleaned_text: 过滤废词后的文本
        - core_intent: 核心意图（处理意图切换后）
        - is_complete: 是否完整
        - has_intent_switch: 是否有意图切换
        """
        from services.text_preprocessor import preprocess_transcription
        return preprocess_transcription(text)
    
    @staticmethod
    def should_wait_for_more(text: str) -> tuple:
        """
        判断是否应该继续等待用户输入
        
        Returns:
            (should_wait: bool, reason: str)
        """
        from services.text_preprocessor import should_wait_for_more_input
        return should_wait_for_more_input(text)

    @staticmethod
    def parse(
        response_text: str, 
        transcription: str = "",
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> ProcessingResult:
        """解析 LLM 响应，并分析对话节奏"""
        result = ProcessingResult()
        
        try:
            # 先尝试修复占位符
            fixed_text = ResponseParser._fix_json_placeholders(response_text)
            
            # 尝试直接解析整个响应为 JSON
            try:
                parsed = json.loads(fixed_text)
            except json.JSONDecodeError:
                # 如果失败，尝试提取 JSON 部分
                json_match = re.search(r'\{[\s\S]*\}', fixed_text)
                if json_match:
                    parsed = json.loads(json_match.group())
                else:
                    raise json.JSONDecodeError("No JSON found", fixed_text, 0)
            
            # 解析字段
            result.transcription = parsed.get("transcription", transcription) or transcription
            
            # 处理 evaluation
            eval_data = parsed.get("evaluation", {})
            if isinstance(eval_data, dict):
                # 过滤冗余修正（original == corrected）
                corrections = eval_data.get("corrections", [])
                filtered_corrections = []
                for corr in corrections:
                    if isinstance(corr, dict):
                        original = corr.get("original", "").strip()
                        corrected = corr.get("corrected", "").strip()
                        # 如果 original 和 corrected 相同，跳过（冗余修正）
                        if original.lower() != corrected.lower() or original != corrected:
                            filtered_corrections.append(corr)
                        else:
                            logger.debug(f"过滤冗余修正: {original} → {corrected}")
                    else:
                        filtered_corrections.append(corr)
                
                result.evaluation = {
                    "overall_score": eval_data.get("overall_score", 50),
                    "cefr_level": eval_data.get("cefr_level", "A2"),
                    "strengths": eval_data.get("strengths", []),
                    "weaknesses": eval_data.get("weaknesses", []),
                    "corrections": filtered_corrections,  # 使用过滤后的修正
                    "good_expressions": eval_data.get("good_expressions", []),
                    "encouragement": eval_data.get("encouragement", "")
                }
            
            result.interests = parsed.get("interests", [])
            result.ai_feedback = parsed.get("response", "")
            result.next_question = parsed.get("next_question", "")
            
            # 组合完整回复
            if result.ai_feedback:
                result.full_response = result.ai_feedback
            elif result.next_question:
                result.full_response = result.next_question
            else:
                logger.warning(f"解析后 response 和 next_question 都为空, parsed keys: {list(parsed.keys())}")
                logger.warning(f"原始响应前200字符: {response_text[:200]}")
                result.full_response = "I'm sorry, I couldn't understand that. Could you please try again?"
                
            logger.info(f"[解析成功] 转录: {result.transcription[:30] if result.transcription else 'None'}...")
                    
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}")
            
            # 尝试用正则提取各个字段
            # 1. 提取 transcription
            extracted_transcription = ResponseParser._extract_transcription(response_text)
            if extracted_transcription:
                result.transcription = extracted_transcription
            elif transcription:
                result.transcription = transcription
            
            # 2. 提取 response
            extracted_response = ResponseParser._extract_response_text(response_text)
            if extracted_response:
                result.full_response = extracted_response
                logger.info(f"[正则提取] response: {extracted_response[:50]}...")
            else:
                # 最后的回退：检查是否是纯文本响应
                if not response_text.startswith("{") and not response_text.startswith("```"):
                    result.full_response = response_text
                else:
                    result.full_response = "I'm sorry, I couldn't process that. Could you please try again?"
            
            # 3. 提取 evaluation
            result.evaluation = ResponseParser._extract_evaluation(response_text)
            
            # 过滤冗余修正
            corrections = result.evaluation.get("corrections", [])
            filtered_corrections = []
            for corr in corrections:
                if isinstance(corr, dict):
                    original = corr.get("original", "").strip()
                    corrected = corr.get("corrected", "").strip()
                    if original.lower() != corrected.lower() or original != corrected:
                        filtered_corrections.append(corr)
                    else:
                        logger.debug(f"过滤冗余修正: {original} → {corrected}")
                else:
                    filtered_corrections.append(corr)
            result.evaluation["corrections"] = filtered_corrections
            
            logger.info(f"[正则提取] 转录: {result.transcription[:30] if result.transcription else 'None'}...")
        
        # 对话节奏分析（阶段 2）
        result.rhythm_hints = ConversationRhythmAnalyzer.analyze(
            result.transcription, 
            conversation_history
        )
        
        return result


class UnifiedProcessor:
    """
    统一处理器 - 两套服务的入口
    
    支持的后端：
    - DashScope: 阿里云 qwen-audio-turbo-latest（推荐，支持真正的流式输出）
    - OpenRouter: GPT-4o Audio
    """
    
    def __init__(self, api_service = None, service_type: Optional[str] = None):
        """
        初始化
        
        Args:
            api_service: 已创建的 API 服务实例（可选）
            service_type: 服务类型 "dashscope" 或 "openrouter"（可选，默认从配置读取）
        """
        self.service_type = service_type or settings.llm_service
        
        if api_service:
            self.api_service = api_service
        else:
            self.api_service = self._create_service()
        
        self.parser = ResponseParser()
        logger.info(f"统一处理器初始化: 使用 {self.service_type} 服务")
    
    @staticmethod
    def is_sentence_complete(text: str) -> bool:
        """检查句子是否完整（代理到 ResponseParser）"""
        return ResponseParser.is_sentence_complete(text)
    
    @staticmethod
    def preprocess_text(text: str):
        """预处理转录文本（代理到 ResponseParser）"""
        return ResponseParser.preprocess_text(text)
    
    @staticmethod
    def should_wait_for_more(text: str) -> tuple:
        """判断是否应该继续等待用户输入（代理到 ResponseParser）"""
        return ResponseParser.should_wait_for_more(text)
    
    def _create_service(self):
        """根据配置创建 API 服务"""
        if self.service_type == "dashscope":
            from services.dashscope_audio import create_dashscope_service
            return create_dashscope_service()
        elif self.service_type == "qwen-omni":
            from services.qwen_omni_audio import create_qwen_omni_service
            return create_qwen_omni_service()
        else:
            from services.openrouter_audio import create_openrouter_service
            return create_openrouter_service()
    
    def process_audio(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> ProcessingResult:
        """
        处理音频输入（OpenRouter Audio 模式）
        
        流程：音频 → GPT-4o Audio → 解析结果
        """
        system_prompt = get_system_prompt(user_profile, conversation_history)
        user_prompt = get_user_prompt_for_audio()
        
        response = self.api_service.call_with_audio(
            audio_data=audio_data,
            audio_format=audio_format,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            conversation_history=conversation_history
        )
        
        return self.parser.parse(response, conversation_history=conversation_history)
    
    def process_audio_stream(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式处理音频输入
        
        Yields:
            {"type": "chunk", "content": "..."} - 响应片段
            {"type": "complete", "data": ProcessingResult} - 完整结果
        """
        system_prompt = get_system_prompt(user_profile, conversation_history)
        user_prompt = get_user_prompt_for_audio()
        
        full_response = ""
        
        for chunk in self.api_service.call_with_audio_stream(
            audio_data=audio_data,
            audio_format=audio_format,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            conversation_history=conversation_history
        ):
            full_response += chunk
            yield {"type": "chunk", "content": chunk}
        
        result = self.parser.parse(full_response, conversation_history=conversation_history)
        yield {"type": "complete", "data": result}
    
    def process_text(
        self,
        user_text: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> ProcessingResult:
        """
        处理文本输入（标准流程模式）
        
        流程：文本 → LLM → 解析结果
        """
        system_prompt = get_system_prompt(user_profile, conversation_history)
        user_prompt = get_user_prompt_for_text(user_text)
        
        response = self.api_service.call_with_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            conversation_history=conversation_history
        )
        
        return self.parser.parse(response, transcription=user_text, conversation_history=conversation_history)
    
    def process_text_stream(
        self,
        user_text: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式处理文本输入
        
        Yields:
            {"type": "chunk", "content": "..."} - 响应片段
            {"type": "complete", "data": ProcessingResult} - 完整结果
        """
        system_prompt = get_system_prompt(user_profile, conversation_history)
        user_prompt = get_user_prompt_for_text(user_text)
        
        full_response = ""
        
        for chunk in self.api_service.call_with_text_stream(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            conversation_history=conversation_history
        ):
            full_response += chunk
            yield {"type": "chunk", "content": chunk}
        
        result = self.parser.parse(full_response, transcription=user_text, conversation_history=conversation_history)
        yield {"type": "complete", "data": result}
    
    def generate_initial_question(
        self,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        动态生成初始问题（通过 LLM）
        
        根据用户画像生成个性化的开场问题
        """
        prompt = get_initial_question_prompt(user_profile)
        
        try:
            response = self.api_service.call_with_text(
                system_prompt="你是一个友好的英语口语教练，正在为学生生成一个开场问题。",
                user_prompt=prompt
            )
            return response.strip()
        except Exception as e:
            logger.error(f"生成初始问题失败: {e}")
            # 回退到默认问题
            return "Hello! I'm excited to chat with you today. What's something interesting that happened to you recently? (你好！我很高兴今天能和你聊天。最近有什么有趣的事情发生吗？)"
    
    def generate_initial_question_stream(
        self,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式生成初始问题（S2S - 同时输出文本和音频）
        
        使用 Qwen-Omni 保持音色一致
        
        Yields:
            Dict with keys:
            - "text": 文本片段 (str or None)
            - "audio": 音频数据 base64 (str or None)
        """
        prompt = get_initial_question_prompt(user_profile)
        
        system_prompt = "You are a warm, friendly English speaking coach."
        
        try:
            # 检查 api_service 是否支持 S2S
            if hasattr(self.api_service, 'call_text_to_speech_stream'):
                # 使用 Qwen-Omni 的 S2S 模式（文本+音频）
                for chunk in self.api_service.call_text_to_speech_stream(
                    system_prompt=system_prompt,
                    user_prompt=prompt
                ):
                    yield chunk
            else:
                # 回退到纯文本模式
                for chunk in self.api_service.call_with_text_stream(
                    system_prompt=system_prompt,
                    user_prompt=prompt
                ):
                    yield {"text": chunk, "audio": None}
        except Exception as e:
            logger.error(f"生成初始问题流式失败: {e}")
            yield {"text": "Hello! What's something interesting that happened to you recently?", "audio": None}
    
    def translate_only(self, english_text: str) -> str:
        """
        翻译轨 - 仅翻译，返回中文
        
        Args:
            english_text: 英文文本
            
        Returns:
            中文翻译
        """
        return self.translate_text(english_text)
    
    # ==========================================
    # 四轨并行接口
    # ==========================================
    
    def transcribe_audio(
        self,
        audio_data: bytes,
        audio_format: str = "wav"
    ) -> str:
        """
        转录轨 - 语音转文字
        
        特点：
        - 零自动纠错，保留原始错误
        - 独立于交互轨，可并行执行
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            
        Returns:
            原始转录文本
        """
        system_prompt = get_transcription_system_prompt()
        user_prompt = get_transcription_user_prompt()
        
        try:
            response = self.api_service.call_with_audio(
                audio_data=audio_data,
                audio_format=audio_format,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
            return response.strip()
        except Exception as e:
            logger.error(f"转录失败: {e}")
            return ""
    
    def translate_text(self, english_text: str, user_level: str = "A1") -> str:
        """
        翻译轨 - 将英文翻译为中文
        
        特点：
        - 轻量级，快速响应
        - 独立于评估轨，可并行执行
        - 根据用户等级调整翻译风格
        
        Args:
            english_text: 需要翻译的英文（通常是 AI 回复）
            user_level: 用户 CEFR 等级
            
        Returns:
            中文翻译
        """
        system_prompt = get_translation_system_prompt(user_level)
        user_prompt = get_translation_user_prompt(english_text)
        
        try:
            response = self.api_service.call_with_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
            return response.strip()
        except Exception as e:
            logger.error(f"翻译失败: {e}")
            return ""
    
    def evaluate_only(
        self,
        transcription: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        评估轨 - 仅评估，不生成回复
        
        特点：
        - 专注于语言评估
        - 独立于交互轨，可并行执行
        - JSON 输出保证：失败时重试
        
        Args:
            transcription: 用户语音转录
            conversation_history: 对话历史
            user_profile: 用户画像
            max_retries: 最大重试次数
            
        Returns:
            评估结果字典，包含 evaluation 字段和 interests 字段
        """
        system_prompt = get_evaluation_system_prompt()
        user_prompt = get_evaluation_user_prompt(transcription, conversation_history, user_profile)
        
        default_result = {
            "overall_score": 50,
            "cefr_level": "A2",
            "corrections": [],
            "good_expressions": [],
            "encouragement": "Keep practicing!",
            "interests": [],  # 兴趣点
            "strengths": [],  # 优点（用于用户画像，不在前端展示）
            "weaknesses": []  # 缺点（用于用户画像，不在前端展示）
        }
        
        for attempt in range(max_retries + 1):
            try:
                response = self.api_service.call_with_text(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt
                )
                
                # 尝试解析 JSON
                result = self.parser.parse(response, transcription=transcription, conversation_history=conversation_history)
                
                # 验证关键字段存在
                if result.evaluation and result.evaluation.get("overall_score") is not None:
                    # 将 interests 合并到 evaluation 中返回
                    # strengths 和 weaknesses 已经在 evaluation 内部
                    eval_with_extras = result.evaluation.copy()
                    eval_with_extras["interests"] = result.interests or []
                    # 添加节奏提示
                    eval_with_extras["rhythm_hints"] = result.rhythm_hints
                    # 确保 strengths 和 weaknesses 存在
                    if "strengths" not in eval_with_extras:
                        eval_with_extras["strengths"] = []
                    if "weaknesses" not in eval_with_extras:
                        eval_with_extras["weaknesses"] = []
                    return eval_with_extras
                
                # 如果解析成功但缺少关键字段，重试
                if attempt < max_retries:
                    logger.warning(f"评估结果缺少关键字段，重试 {attempt + 1}/{max_retries}")
                    continue
                    
            except json.JSONDecodeError as e:
                if attempt < max_retries:
                    logger.warning(f"JSON 解析失败，重试 {attempt + 1}/{max_retries}: {e}")
                    continue
                logger.error(f"评估 JSON 解析最终失败: {e}")
            except Exception as e:
                logger.error(f"评估失败: {e}")
                break
        
        return default_result
    
    def evaluate_audio(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        评估轨（音频输入版本）- 直接从音频转录+评估
        
        特点：
        - 直接音频输入，保留语音特征（语调、流利度、停顿等）
        - 同时完成转录和评估
        - JSON 输出保证
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            conversation_history: 对话历史
            user_profile: 用户画像
            max_retries: 最大重试次数
            
        Returns:
            评估结果字典，包含 transcription 和 evaluation 字段
        """
        from prompts.templates import get_evaluation_system_prompt, get_evaluation_user_prompt
        
        system_prompt = get_evaluation_system_prompt()
        # 不传入 transcription，让模型从音频直接转录+评估
        user_prompt = get_evaluation_user_prompt("", conversation_history, user_profile)
        
        # 限制对话历史长度：只保留最近 4 轮（8 条消息）
        # 评估轨使用 modalities=["text"]，有更多时间理解，但限制历史仍有助于聚焦当前输入
        limited_history = None
        if conversation_history:
            limited_history = conversation_history[-8:] if len(conversation_history) > 8 else conversation_history
        
        default_result = {
            "transcription": "",
            "overall_score": 50,
            "cefr_level": "A2",
            "corrections": [],
            "good_expressions": [],
            "encouragement": "Keep practicing!",
            "interests": [],
            "strengths": [],
            "weaknesses": []
        }
        
        for attempt in range(max_retries + 1):
            try:
                # 直接用音频调用 API
                response = self.api_service.call_with_audio(
                    audio_data=audio_data,
                    audio_format=audio_format,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    conversation_history=limited_history  # 使用限制后的历史
                )
                
                logger.info(f"[评估轨] 原始响应: {response[:200]}...")
                
                # 解析 JSON
                result = self.parser.parse(response, conversation_history=limited_history)
                
                if result.evaluation and result.evaluation.get("overall_score") is not None:
                    eval_result = result.evaluation.copy()
                    eval_result["transcription"] = result.transcription or ""
                    eval_result["interests"] = result.interests or []
                    eval_result["rhythm_hints"] = result.rhythm_hints
                    if "strengths" not in eval_result:
                        eval_result["strengths"] = []
                    if "weaknesses" not in eval_result:
                        eval_result["weaknesses"] = []
                    
                    logger.info(f"[评估轨] 转录: {eval_result['transcription'][:50]}...")
                    return eval_result
                
                if attempt < max_retries:
                    logger.warning(f"评估结果缺少关键字段，重试 {attempt + 1}/{max_retries}")
                    continue
                    
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"评估失败，重试 {attempt + 1}/{max_retries}: {e}")
                    continue
                logger.error(f"评估最终失败: {e}")
        
        return default_result
    
    def evaluate_audio_no_context(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        user_profile: Optional[Dict[str, Any]] = None,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        评估轨（无上下文版本）- 只评估当前句子，不依赖历史对话
        
        特点：
        - 无历史上下文，专注于当前句子的语言质量评估
        - 更快的响应速度（减少 token 消耗）
        - 适用于异步评估场景
        - 直接从音频转录+评估，独立工作
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            user_profile: 用户画像（仅用于了解用户等级）
            max_retries: 最大重试次数
            
        Returns:
            评估结果字典，包含 transcription 和 evaluation 字段
        """
        from prompts.templates import get_evaluation_system_prompt_no_context, get_evaluation_user_prompt_no_context
        
        system_prompt = get_evaluation_system_prompt_no_context()
        user_prompt = get_evaluation_user_prompt_no_context(user_profile)
        
        default_result = {
            "transcription": "",
            "overall_score": 50,
            "cefr_level": "A2",
            "corrections": [],
            "good_expressions": [],
            "encouragement": "Keep practicing!",
            "interests": [],
            "strengths": [],
            "weaknesses": []
        }
        
        for attempt in range(max_retries + 1):
            try:
                # 直接用音频调用 API，不传历史
                response = self.api_service.call_with_audio(
                    audio_data=audio_data,
                    audio_format=audio_format,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    conversation_history=None  # 无历史上下文
                )
                
                logger.info(f"[评估轨-无上下文] 原始响应: {response[:200]}...")
                
                # 解析 JSON（无历史上下文）
                result = self.parser.parse(response)
                
                if result.evaluation and result.evaluation.get("overall_score") is not None:
                    eval_result = result.evaluation.copy()
                    eval_result["transcription"] = result.transcription or ""
                    eval_result["interests"] = result.interests or []
                    eval_result["rhythm_hints"] = result.rhythm_hints
                    if "strengths" not in eval_result:
                        eval_result["strengths"] = []
                    if "weaknesses" not in eval_result:
                        eval_result["weaknesses"] = []
                    
                    logger.info(f"[评估轨-无上下文] 转录: {eval_result['transcription'][:50]}...")
                    return eval_result
                
                if attempt < max_retries:
                    logger.warning(f"评估结果缺少关键字段，重试 {attempt + 1}/{max_retries}")
                    continue
                    
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"评估失败，重试 {attempt + 1}/{max_retries}: {e}")
                    continue
                logger.error(f"评估最终失败: {e}")
        
        return default_result
    
    def interact_stream(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        交互轨 - 流式生成英文回复
        
        特点：
        - 流式输出，低延迟
        - 纯英文回复
        - 不包含评估和转录
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            conversation_history: 对话历史
            user_profile: 用户画像
            
        Yields:
            Dict with keys:
            - "text": 文本片段 (str or None)
            - "audio": 音频数据 base64 (str or None)
        """
        system_prompt = get_interaction_system_prompt(user_profile)
        
        # 限制对话历史长度：保留最近 3 轮（6 条消息），平衡上下文和专注度
        # 扩大历史窗口以支持用户引用之前的内容（如 "use what I said before"）
        # 但不过多保留历史，避免模型过度依赖历史而忽略当前音频
        limited_history = None
        if conversation_history:
            # 保留最近 3 轮（6 条消息：3轮用户+AI对话）
            limited_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
        
        # 使用限制后的历史构建 user_prompt，确保 user_prompt 和 messages 数组中的历史一致
        user_prompt = get_user_prompt_for_audio(limited_history, user_profile)
        
        try:
            # 检查服务是否支持 output_audio 参数（只有 QwenOmniAudioService 支持）
            import inspect
            sig = inspect.signature(self.api_service.call_with_audio_stream)
            supports_output_audio = 'output_audio' in sig.parameters
            
            kwargs = {
                "audio_data": audio_data,
                "audio_format": audio_format,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "conversation_history": limited_history,
            }
            if supports_output_audio:
                kwargs["output_audio"] = True  # 启用 S2S
            
            for chunk in self.api_service.call_with_audio_stream(**kwargs):
                yield chunk
        except Exception as e:
            logger.error(f"交互轨流式调用失败: {e}")
            yield {"text": "I'm sorry, I couldn't process that. Could you please try again?", "audio": None}
    
    def interact_text_stream(
        self,
        transcription: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        交互轨（文本输入版本）- 使用 ASR 转录文本作为输入
        
        用于：豆包 ASR → GPT-4o → MiniMax TTS 链路
        
        Args:
            transcription: ASR 转录文本
            conversation_history: 对话历史
            user_profile: 用户画像
            
        Yields:
            Dict with keys:
            - "text": 文本片段 (str or None)
            - "audio": 音频数据 base64 (str or None, 通常为 None)
        """
        system_prompt = get_interaction_system_prompt(user_profile)
        
        # 限制对话历史长度
        limited_history = None
        if conversation_history:
            limited_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
        
        # 构建 user_prompt - 文本输入版本
        # 构建历史对话部分
        history_section = ""
        if limited_history and len(limited_history) > 0:
            lines = []
            for msg in limited_history:
                role = "User" if msg.get('role') == 'user' else "Coach"
                content = msg.get('content', '')
                lines.append(f"{role}: {content}")
            history_content = "\n".join(lines)
            history_section = f"""═══════════════════════════════════════════════════════
⚠️  BELOW IS HISTORY - FOR REFERENCE ONLY, NOT WHAT TO ANSWER NOW
═══════════════════════════════════════════════════════
## Previous conversation:
{history_content}
═══════════════════════════════════════════════════════
✅  ABOVE IS HISTORY - USE IT ONLY TO UNDERSTAND REFERENCES
═══════════════════════════════════════════════════════

"""
        
        # 构建用户画像部分
        profile_section = ""
        if user_profile:
            level = user_profile.get('cefr_level', 'Unknown')
            interests = user_profile.get('interests', [])
            if isinstance(interests, list):
                interests = [i for i in interests if isinstance(i, str)]
            interests_str = ', '.join(interests[:5]) if interests else 'Unknown'
            profile_section = f"""## User: {level} level, interests: {interests_str}

"""
        
        # 构建完整的 user_prompt，明确标注当前输入
        user_prompt = f"""{history_section}{profile_section}═══════════════════════════════════════════════════════
🎯  THIS IS THE CURRENT INPUT - ANSWER THIS NOW
═══════════════════════════════════════════════════════
## Current user message:
{transcription}

**CRITICAL: Respond naturally to what the user said above. Do NOT repeat their words. Continue the conversation.**
"""
        
        try:
            for text_chunk in self.api_service.call_with_text_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                conversation_history=limited_history,
            ):
                yield {"text": text_chunk, "audio": None}
        except Exception as e:
            logger.error(f"交互轨(文本)流式调用失败: {e}")
            yield {"text": "I'm sorry, I couldn't process that. Could you please try again?", "audio": None}
    
    def transcribe_only(
        self,
        audio_data: bytes,
        audio_format: str = "wav"
    ) -> str:
        """
        转录轨 - 纯语音转文字（非流式）
        
        特点：
        - 零自动纠错，保留原始错误
        - 保留中文词汇和填充词
        - 使用 Qwen-Omni（不输出音频，只输出文本）
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            
        Returns:
            转录文本
        """
        system_prompt = get_transcription_system_prompt()
        user_prompt = get_transcription_user_prompt()
        
        full_text = ""
        try:
            for chunk in self.api_service.call_with_audio_stream(
                audio_data=audio_data,
                audio_format=audio_format,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_audio=False  # 不输出音频，只转录
            ):
                # Qwen-Omni 返回 {"text": ..., "audio": ...}
                if isinstance(chunk, dict):
                    text = chunk.get("text", "")
                    if text:
                        full_text += text
                elif isinstance(chunk, str):
                    full_text += chunk
            return full_text.strip()
        except Exception as e:
            logger.error(f"转录轨调用失败: {e}")
            return ""
    
    def transcribe_audio_stream(
        self,
        audio_data: bytes,
        audio_format: str = "wav"
    ) -> Generator[str, None, None]:
        """
        转录轨 - 流式语音转文字
        
        特点：
        - 零自动纠错，保留原始错误
        - 保留中文词汇
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            
        Yields:
            转录文本片段
        """
        system_prompt = get_transcription_system_prompt()
        user_prompt = get_transcription_user_prompt()
        
        try:
            for chunk in self.api_service.call_with_audio_stream(
                audio_data=audio_data,
                audio_format=audio_format,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_audio=False
            ):
                # Qwen-Omni 返回 {"text": ..., "audio": ...}
                if isinstance(chunk, dict):
                    text = chunk.get("text", "")
                    if text:
                        yield text
                elif isinstance(chunk, str):
                    yield chunk
        except Exception as e:
            logger.error(f"转录轨流式调用失败: {e}")
            yield ""
    
    def translate_stream(
        self,
        english_text: str,
        user_level: str = "A1"
    ) -> Generator[str, None, None]:
        """
        翻译轨 - 流式英译中
        
        Args:
            english_text: 英文文本
            user_level: 用户 CEFR 等级
            
        Yields:
            中文翻译片段
        """
        system_prompt = get_translation_system_prompt(user_level)
        user_prompt = get_translation_user_prompt(english_text)
        
        try:
            for chunk in self.api_service.call_with_text_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            ):
                yield chunk
        except Exception as e:
            logger.error(f"翻译轨流式调用失败: {e}")
            yield ""
    
    def evaluate_stream(
        self,
        transcription: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Generator[str, None, None]:
        """
        评估轨 - 流式评估
        
        Args:
            transcription: 用户语音转录
            conversation_history: 对话历史
            user_profile: 用户画像
            
        Yields:
            评估 JSON 片段
        """
        system_prompt = get_evaluation_system_prompt()
        user_prompt = get_evaluation_user_prompt(transcription, conversation_history, user_profile)
        
        try:
            for chunk in self.api_service.call_with_text_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            ):
                yield chunk
        except Exception as e:
            logger.error(f"评估轨流式调用失败: {e}")
            yield '{"overall_score": 50, "cefr_level": "A2"}'


class UserProfileUpdater:
    """用户画像更新器 - 使用加权平均，避免单轮波动"""
    
    # 加权系数：历史分数权重 vs 本轮分数权重
    HISTORY_WEIGHT = 0.7  # 历史分数占 70%
    CURRENT_WEIGHT = 0.3  # 本轮分数占 30%
    
    # CEFR 等级对应的分数范围（用于等级判定）
    # 按照新标准：Pre-A1: 0-14, A1: 15-29, A2: 30-44, B1: 45-59, B2: 60-74, C1: 75-89, C2: 90-100
    CEFR_SCORE_MAP = {
        "Pre-A1": (0, 15),
        "A1": (15, 30),
        "A2": (30, 45),
        "B1": (45, 60),
        "B2": (60, 75),
        "C1": (75, 90),
        "C2": (90, 101)  # 101 作为上限，确保 100 分包含在内
    }
    
    @staticmethod
    def _score_to_cefr(score: float) -> str:
        """根据分数计算 CEFR 等级"""
        for level, (min_score, max_score) in UserProfileUpdater.CEFR_SCORE_MAP.items():
            if min_score <= score < max_score:
                return level
        return "C2" if score >= 90 else "Pre-A1"
    
    @staticmethod
    def update(profile: Dict[str, Any], result: ProcessingResult) -> Dict[str, Any]:
        """
        根据处理结果更新用户画像
        
        使用加权平均计算分数，避免单轮表现波动过大：
        - 新分数 = 历史分数 * 0.7 + 本轮分数 * 0.3
        - CEFR 等级根据加权后的分数重新计算
        """
        eval_data = result.evaluation
        
        # 加权平均计算分数
        if eval_data.get("overall_score") is not None:
            old_score = profile.get("overall_score", 50.0)  # 默认 50 分
            new_score = eval_data["overall_score"]
            
            # 如果是新用户（没有历史分数），直接使用本轮分数
            if old_score == 0 or profile.get("conversation_count", 0) == 0:
                weighted_score = new_score
            else:
                weighted_score = (
                    old_score * UserProfileUpdater.HISTORY_WEIGHT + 
                    new_score * UserProfileUpdater.CURRENT_WEIGHT
                )
            
            profile["overall_score"] = round(weighted_score, 1)
            
            # 根据加权后的分数重新计算 CEFR 等级
            profile["cefr_level"] = UserProfileUpdater._score_to_cefr(weighted_score)
        
        # 增加对话轮次计数（用于判断是否新用户）
        profile["round_count"] = profile.get("round_count", 0) + 1
        
        # 合并强项（去重，保留最近5个）
        new_strengths = [s for s in eval_data.get("strengths", []) if isinstance(s, str)]
        existing = [s for s in profile.get("strengths", []) if isinstance(s, str)]
        profile["strengths"] = list(dict.fromkeys(existing + new_strengths))[-5:]
        
        # 合并弱项
        new_weaknesses = [w for w in eval_data.get("weaknesses", []) if isinstance(w, str)]
        existing = [w for w in profile.get("weaknesses", []) if isinstance(w, str)]
        profile["weaknesses"] = list(dict.fromkeys(existing + new_weaknesses))[-5:]
        
        # 合并兴趣（保留最近10个）- 只保留字符串类型
        new_interests = [i for i in result.interests if isinstance(i, str)]
        existing_interests = []
        for item in profile.get("interests", []):
            if isinstance(item, str):
                existing_interests.append(item)
            elif isinstance(item, dict):
                # 从 dict 中提取 tags
                tags = item.get("tags", [])
                existing_interests.extend([t for t in tags if isinstance(t, str)])
        profile["interests"] = list(dict.fromkeys(existing_interests + new_interests))[-10:]
        
        return profile


# 便捷函数
def create_processor(api_service = None, service_type: Optional[str] = None) -> UnifiedProcessor:
    """
    创建统一处理器
    
    Args:
        api_service: 已创建的 API 服务实例（可选）
        service_type: 服务类型 "dashscope" 或 "openrouter"（可选，默认从配置读取）
    """
    return UnifiedProcessor(api_service, service_type)
