"""
文本处理工具 - 处理中英文混杂等文本预处理
"""
import re
from typing import Dict, List, Tuple


def detect_language_mix(text: str) -> Dict[str, any]:
    """
    检测文本中的中英文混杂情况
    
    Returns:
        {
            "has_chinese": bool,
            "has_english": bool,
            "is_mixed": bool,
            "chinese_ratio": float,
            "english_ratio": float
        }
    """
    # 中文字符正则
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    # 英文字符正则（包括单词）
    english_pattern = re.compile(r'[a-zA-Z]+')
    
    chinese_chars = len(chinese_pattern.findall(text))
    english_chars = len(english_pattern.findall(text))
    total_chars = len(text)
    
    has_chinese = chinese_chars > 0
    has_english = english_chars > 0
    is_mixed = has_chinese and has_english
    
    chinese_ratio = chinese_chars / total_chars if total_chars > 0 else 0
    english_ratio = english_chars / total_chars if total_chars > 0 else 0
    
    return {
        "has_chinese": has_chinese,
        "has_english": has_english,
        "is_mixed": is_mixed,
        "chinese_ratio": chinese_ratio,
        "english_ratio": english_ratio,
        "chinese_count": chinese_chars,
        "english_count": english_chars
    }


def extract_language_parts(text: str) -> Dict[str, List[str]]:
    """
    提取文本中的中英文部分
    
    Returns:
        {
            "chinese_parts": List[str],
            "english_parts": List[str],
            "mixed_parts": List[str]
        }
    """
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    english_pattern = re.compile(r'[a-zA-Z]+(?:\s+[a-zA-Z]+)*')
    
    chinese_parts = chinese_pattern.findall(text)
    english_parts = english_pattern.findall(text)
    
    # 识别混合部分（中英文相邻）
    mixed_pattern = re.compile(r'[\u4e00-\u9fff]+[a-zA-Z]+|[a-zA-Z]+[\u4e00-\u9fff]+')
    mixed_parts = mixed_pattern.findall(text)
    
    return {
        "chinese_parts": chinese_parts,
        "english_parts": english_parts,
        "mixed_parts": mixed_parts
    }


def normalize_mixed_text(text: str) -> str:
    """
    规范化中英文混杂文本
    - 在中英文之间添加空格
    - 保持原有内容不变
    """
    # 在中文字符和英文字符之间添加空格
    normalized = re.sub(r'([\u4e00-\u9fff])([a-zA-Z])', r'\1 \2', text)
    normalized = re.sub(r'([a-zA-Z])([\u4e00-\u9fff])', r'\1 \2', normalized)
    
    return normalized.strip()


def is_valid_mixed_usage(text: str) -> Tuple[bool, str]:
    """
    判断中英文混杂使用是否合理
    
    Returns:
        (是否合理, 原因说明)
    """
    analysis = detect_language_mix(text)
    
    if not analysis["is_mixed"]:
        return True, "纯中文或纯英文，无需判断混合使用"
    
    # 如果英文比例很高，中文只是辅助说明，这是合理的
    if analysis["english_ratio"] > 0.7:
        return True, "以英文为主，中文辅助，合理"
    
    # 如果中文比例很高，英文只是个别单词，这也是合理的
    if analysis["chinese_ratio"] > 0.7:
        return True, "以中文为主，英文单词补充，合理"
    
    # 如果中英文比例相当，需要进一步判断
    # 这里可以添加更复杂的逻辑
    return True, "中英文混合使用，需要评估其恰当性"





