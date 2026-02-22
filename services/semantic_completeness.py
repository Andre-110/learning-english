"""
语义完整性检测服务

完全对照 UserGenie 的 isSemanticComplete 实现。
规则优先，尽量避免 API 调用延迟。
"""
from typing import Tuple
from services.utils.logger import get_logger

logger = get_logger("services.semantic_completeness")


class SemanticCompletenessChecker:
    """
    语义完整性检测器
    
    规则:
    1. 空文本 → 不完整
    2. 以不完整结尾词结束 → 不完整 (介词/连词/冠词/情态动词/be动词/助动词/中文结尾词)
    3. 完整短语 → 完整 (yes/no/ok/是的/不是/etc)
    4. 5词以上+标点结尾 → 完整
    5. 3词以上 → 默认完整
    6. 短句 → 默认完整
    """
    
    # 
    INCOMPLETE_ENDINGS = frozenset([
        # 介词
        'to', 'for', 'with', 'in', 'on', 'at', 'by', 'from', 'of', 'about', 'into',
        # 连词
        'and', 'but', 'or', 'because', 'so', 'if', 'when', 'while', 'although',
        # 冠词
        'the', 'a', 'an',
        # 情态动词（单独出现时）
        'can', 'could', 'will', 'would', 'shall', 'should', 'may', 'might', 'must',
        # be 动词（通常后面有内容）
        'is', 'are', 'was', 'were', 'am', 'be',
        # 助动词
        'have', 'has', 'had', 'do', 'does', 'did',
        # 中文不完整结尾
        '的', '是', '在', '和', '与', '或', '但', '因为', '所以', '如果', '要', '想', '会', '能',
    ])
    
    # ✅ 完整短语 - 完全对照 UserGenie
    COMPLETE_PHRASES = frozenset([
        'yes', 'no', 'ok', 'okay', 'sure', 'right', 'exactly',
        'i agree', 'i disagree', "i don't know", 'thank you', 'thanks',
        '是的', '不是', '好的', '可以', '不行', '谢谢', '知道了', '明白',
    ])
    
    def __init__(self):
        pass  # 纯规则检测，无需初始化
    
    async def check_async(self, text: str, context: str = "") -> Tuple[bool, float, str]:
        """异步检查语义完整性"""
        return self.check(text, context)
    
    def check(self, text: str, context: str = "") -> Tuple[bool, float, str]:
        """
        检查语义完整性 - 完全对照 UserGenie 的 isSemanticComplete
        
        Returns:
            (is_complete, confidence, reason)
        """
        # 1. 空文本检查
        if not text or not text.strip():
            return False, 0.2, "Empty text"
        
        # 2. 清理文本
        import re
        text_lower = text.strip().lower()
        text_lower = re.sub(r'[.,!?]+$', '', text_lower)  # 去除末尾标点（用于词检测）
        words = [w for w in text_lower.split() if w]
        
        if not words:
            return False, 0.2, "Empty after cleanup"
        
        last_word = words[-1]
        
        # 3. 不完整结尾词检测
        if last_word in self.INCOMPLETE_ENDINGS:
            logger.info(f"[语义检测] 不完整结尾: '{last_word}' in '{text[:40]}...'")
            return False, 0.85, f"Ends with '{last_word}'"
        
        # 4. 完整短语检测
        if text_lower in self.COMPLETE_PHRASES:
            return True, 0.95, "Complete phrase"
        
        # 5. 长句+标点 → 完整
        original_text = text.strip()
        if len(words) >= 5 and original_text[-1] in '.!?。！？':
            return True, 0.9, "Ends with punctuation"
        
        # 6. 中等长度句子 → 默认完整
        if len(words) >= 3:
            return True, 0.7, "Sufficient length"
        
        # 7. 短句 → 默认完整
        return True, 0.6, "Short sentence"


# 全局单例
_checker: SemanticCompletenessChecker = None


def get_semantic_checker() -> SemanticCompletenessChecker:
    """获取语义检测器单例"""
    global _checker
    if _checker is None:
        _checker = SemanticCompletenessChecker()
    return _checker
