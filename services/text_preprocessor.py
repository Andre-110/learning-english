"""
文本预处理器

处理：
1. 废词过滤（呃、嗯、那个、um、uh 等）
2. 意图切换检测（算了、不用了、never mind 等）
3. 语义完整性增强检查
4. 拖音规范化

这些功能用于改善 VAD 判断和防止 AI 抢话。
"""

import re
from typing import Tuple, List, Optional
from dataclasses import dataclass

from services.utils.logger import get_logger

logger = get_logger("services.text_preprocessor")


# ============================================================================
# 配置常量
# ============================================================================

# 英文废词/填充词
ENGLISH_FILLER_WORDS = {
    # 常见填充词
    'um', 'uh', 'er', 'ah', 'hmm', 'hm', 'mm', 'mmm',
    # 口语过渡词
    'like', 'well', 'so', 'okay', 'ok',
    # 口语表达
    'you know', 'i mean', 'kind of', 'sort of', 'basically',
    # 思考词
    'let me see', 'let me think', 'how do i say', 'how should i say',
}

# 中文废词/填充词（用于双语场景）
CHINESE_FILLER_WORDS = {
    '呃', '嗯', '额', '啊', '哦',
    '那个', '这个', '就是', '然后',
    '我想想', '让我想想', '怎么说呢',
}

# 意图取消词（英文）
ENGLISH_CANCEL_WORDS = {
    'never mind', 'nevermind', 'forget it', 'forget that',
    'wait', 'hold on', 'actually', 'no wait',
    'cancel', 'stop', 'scratch that',
}

# 意图取消词（中文）
CHINESE_CANCEL_WORDS = {
    '算了', '不用了', '等等', '不对', '不是',
    '我再想想', '取消', '停', '等一下',
}

# 未完成句子的结尾词（增强版）
INCOMPLETE_ENDINGS = {
    # 连词
    'and', 'but', 'or', 'because', 'so', 'if', 'when', 'while', 'although',
    'however', 'therefore', 'moreover', 'furthermore', 'thus', 'hence',
    'unless', 'until', 'since', 'as', 'though',
    # 介词
    'to', 'for', 'with', 'in', 'on', 'at', 'by', 'from', 'of',
    'about', 'into', 'through', 'during', 'before', 'after',
    'above', 'below', 'between', 'among', 'under', 'over',
    # 冠词
    'the', 'a', 'an',
    # 代词
    'i', 'you', 'he', 'she', 'we', 'they', 'it',
    # 物主代词
    'my', 'your', 'his', 'her', 'our', 'their', 'its',
    # be动词
    'is', 'are', 'was', 'were', 'am', 'be', 'been', 'being',
    # 助动词
    'can', 'could', 'will', 'would', 'shall', 'should', 'may', 'might',
    'must', 'have', 'has', 'had', 'do', 'does', 'did',
    # 不定词 to
    'to',
    # 关系代词
    'who', 'whom', 'whose', 'which', 'that',
}


@dataclass
class PreprocessResult:
    """预处理结果"""
    original_text: str          # 原始文本
    cleaned_text: str           # 清理后的文本（过滤废词）
    core_intent: str            # 核心意图（如有意图切换，为最新意图）
    is_complete: bool           # 句子是否完整
    has_intent_switch: bool     # 是否有意图切换
    filler_words_found: List[str]  # 发现的废词
    cancel_word_found: Optional[str]  # 发现的取消词
    confidence: float           # 判断置信度 (0-1)


class TextPreprocessor:
    """文本预处理器"""
    
    def __init__(self):
        # 编译正则表达式（提高性能）
        self._filler_pattern_en = self._build_filler_pattern(ENGLISH_FILLER_WORDS)
        self._filler_pattern_zh = self._build_filler_pattern(CHINESE_FILLER_WORDS)
        self._cancel_pattern_en = self._build_pattern(ENGLISH_CANCEL_WORDS)
        self._cancel_pattern_zh = self._build_pattern(CHINESE_CANCEL_WORDS)
        
        logger.info("[TextPreprocessor] 初始化完成")
    
    def _build_filler_pattern(self, words: set) -> re.Pattern:
        """构建废词匹配正则（支持词组）"""
        # 按长度降序排序，优先匹配长词组
        sorted_words = sorted(words, key=len, reverse=True)
        escaped = [re.escape(w) for w in sorted_words]
        pattern = r'\b(' + '|'.join(escaped) + r')\b'
        return re.compile(pattern, re.IGNORECASE)
    
    def _build_pattern(self, words: set) -> re.Pattern:
        """构建匹配正则"""
        sorted_words = sorted(words, key=len, reverse=True)
        escaped = [re.escape(w) for w in sorted_words]
        pattern = r'\b(' + '|'.join(escaped) + r')\b'
        return re.compile(pattern, re.IGNORECASE)
    
    def filter_filler_words(self, text: str) -> Tuple[str, List[str]]:
        """
        过滤废词
        
        Args:
            text: 输入文本
        
        Returns:
            (清理后的文本, 发现的废词列表)
        """
        if not text:
            return "", []
        
        found_fillers = []
        
        # 查找英文废词
        en_matches = self._filler_pattern_en.findall(text)
        found_fillers.extend(en_matches)
        
        # 查找中文废词
        zh_matches = self._filler_pattern_zh.findall(text)
        found_fillers.extend(zh_matches)
        
        # 移除废词
        cleaned = self._filler_pattern_en.sub('', text)
        cleaned = self._filler_pattern_zh.sub('', cleaned)
        
        # 清理多余标点（连续逗号等）
        cleaned = re.sub(r'[,，]+\s*[,，]+', ',', cleaned)
        cleaned = re.sub(r'^[,，\s]+', '', cleaned)  # 开头的逗号
        cleaned = re.sub(r'[,，]\s*[,，]', ',', cleaned)  # 连续逗号
        
        # 清理多余空格
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned, found_fillers
    
    def detect_intent_switch(self, text: str) -> Tuple[bool, Optional[str], str]:
        """
        检测意图切换
        
        Args:
            text: 输入文本
        
        Returns:
            (是否有意图切换, 取消词, 最新意图)
        """
        if not text:
            return False, None, ""
        
        # 查找英文取消词
        en_match = self._cancel_pattern_en.search(text)
        zh_match = self._cancel_pattern_zh.search(text)
        
        cancel_word = None
        cancel_pos = -1
        
        if en_match:
            cancel_word = en_match.group()
            cancel_pos = en_match.end()
        
        if zh_match:
            if cancel_pos < 0 or zh_match.end() > cancel_pos:
                cancel_word = zh_match.group()
                cancel_pos = zh_match.end()
        
        if cancel_word:
            # 取消词后的内容为最新意图
            new_intent = text[cancel_pos:].strip()
            # 清理开头的标点和空格
            new_intent = re.sub(r'^[,，.。!！?？\s]+', '', new_intent)
            return True, cancel_word, new_intent
        
        return False, None, text
    
    def is_sentence_complete(self, text: str) -> Tuple[bool, float]:
        """
        检查句子是否完整（增强版 + Turn Detector）
        
        结合规则判断和 BERT 模型语义判断：
        1. 明确的标点符号 → 高置信度规则判断
        2. 未完成结尾词 → 规则判断
        3. 其他情况 → 使用 Turn Detector 语义判断
        
        Args:
            text: 输入文本
        
        Returns:
            (是否完整, 置信度)
        """
        if not text:
            return False, 0.0
        
        text = text.strip()
        
        # 空文本
        if not text:
            return False, 0.0
        
        # 先过滤废词
        cleaned, fillers = self.filter_filler_words(text)
        
        # 如果过滤后为空，说明只是废词
        if not cleaned:
            return False, 0.2
        
        words = cleaned.split()
        if not words:
            return False, 0.0
        
        # 检查最后一个词
        last_word = words[-1].lower()
        # 去除标点
        last_word_clean = re.sub(r'[^\w]', '', last_word)
        
        # === 规则判断：高置信度情况 ===
        
        # 以未完成结尾词结尾 → 明确未完成
        if last_word_clean in INCOMPLETE_ENDINGS:
            return False, 0.3
        
        # 以问号或感叹号结尾（明确完成）
        if text.endswith('?') or text.endswith('!') or text.endswith('？') or text.endswith('！'):
            return True, 0.95
        
        # 以句号结尾
        if text.endswith('.') or text.endswith('。'):
            return True, 0.9
        
        # === Turn Detector：语义判断 ===
        # 对于没有明确标点的情况，使用 BERT 模型判断
        try:
            from services.turn_detector import get_eou_probability
            eou_prob = get_eou_probability(cleaned)
            
            # 将 Turn Detector 概率转换为置信度
            # eou_prob > 0.5 → 说完了
            # eou_prob < 0.5 → 没说完
            if eou_prob > 0.7:
                # 高概率说完
                return True, min(0.85, 0.5 + eou_prob * 0.4)
            elif eou_prob < 0.3:
                # 高概率没说完
                return False, 0.4
            else:
                # 不确定区间，考虑句子长度
                content_words = [w for w in words if w.lower() not in INCOMPLETE_ENDINGS]
                if len(content_words) >= 3:
                    # 较长句子，偏向认为完整
                    return True, 0.5 + eou_prob * 0.2
                else:
                    # 较短句子，偏向等待
                    return eou_prob > 0.5, 0.4
                    
        except Exception as e:
            # Turn Detector 不可用，回退到规则判断
            logger.debug(f"Turn Detector 不可用: {e}")
        
        # === 回退：规则判断 ===
        confidence = 1.0
        
        # 句子太短（1-2个实词）
        content_words = [w for w in words if w.lower() not in INCOMPLETE_ENDINGS]
        if len(content_words) < 2:
            confidence *= 0.6
        
        # 有废词但也有实质内容
        if fillers and len(content_words) >= 2:
            confidence *= 0.8
        
        # 默认认为完整（但置信度较低）
        return True, min(confidence, 0.7)
    
    def normalize_trailing_sounds(self, text: str) -> str:
        """
        规范化拖音
        
        将 "那——个——" 转换为 "那个"
        """
        if not text:
            return ""
        
        # 移除重复的破折号/横线
        text = re.sub(r'[—\-]{2,}', '', text)
        
        # 移除单个字符后的拖音标记
        text = re.sub(r'(\w)[—\-]+', r'\1', text)
        
        # 移除重复的元音（如 "theeeee" -> "the"）
        # 只处理连续3个以上的重复
        text = re.sub(r'(.)\1{2,}', r'\1', text)
        
        return text.strip()
    
    def preprocess(self, text: str) -> PreprocessResult:
        """
        完整预处理流程
        
        Args:
            text: 输入文本
        
        Returns:
            预处理结果
        """
        if not text:
            return PreprocessResult(
                original_text="",
                cleaned_text="",
                core_intent="",
                is_complete=False,
                has_intent_switch=False,
                filler_words_found=[],
                cancel_word_found=None,
                confidence=0.0
            )
        
        original = text
        
        # 1. 规范化拖音
        text = self.normalize_trailing_sounds(text)
        
        # 2. 检测意图切换
        has_switch, cancel_word, current_intent = self.detect_intent_switch(text)
        
        # 3. 过滤废词
        cleaned, fillers = self.filter_filler_words(current_intent)
        
        # 4. 检查完整性
        is_complete, confidence = self.is_sentence_complete(cleaned)
        
        return PreprocessResult(
            original_text=original,
            cleaned_text=cleaned,
            core_intent=cleaned,
            is_complete=is_complete,
            has_intent_switch=has_switch,
            filler_words_found=fillers,
            cancel_word_found=cancel_word,
            confidence=confidence
        )
    
    def should_wait_for_more(self, text: str) -> Tuple[bool, str]:
        """
        判断是否应该继续等待用户输入
        
        Args:
            text: 当前转录文本
        
        Returns:
            (是否应该等待, 原因)
        """
        result = self.preprocess(text)
        
        # 只有废词，继续等待
        if not result.cleaned_text and result.filler_words_found:
            return True, "only_fillers"
        
        # 句子不完整
        if not result.is_complete:
            return True, "incomplete_sentence"
        
        # 低置信度
        if result.confidence < 0.5:
            return True, "low_confidence"
        
        # 有意图切换但新意图为空
        if result.has_intent_switch and not result.core_intent:
            return True, "intent_switch_pending"
        
        return False, "ready"


# 单例实例
_preprocessor: Optional[TextPreprocessor] = None


def get_text_preprocessor() -> TextPreprocessor:
    """获取文本预处理器单例"""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = TextPreprocessor()
    return _preprocessor


def preprocess_transcription(text: str) -> PreprocessResult:
    """便捷函数：预处理转录文本"""
    return get_text_preprocessor().preprocess(text)


def should_wait_for_more_input(text: str) -> Tuple[bool, str]:
    """便捷函数：判断是否应该继续等待"""
    return get_text_preprocessor().should_wait_for_more(text)

