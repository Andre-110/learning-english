"""
验证工具
"""
from typing import Optional


def validate_user_input(text: str, max_length: int = 2000) -> tuple[bool, Optional[str]]:
    """
    验证用户输入
    
    Returns:
        (是否有效, 错误信息)
    """
    if not text or not text.strip():
        return False, "输入不能为空"
    
    if len(text) > max_length:
        return False, f"输入长度不能超过{max_length}个字符"
    
    return True, None


def validate_conversation_id(conversation_id: str) -> tuple[bool, Optional[str]]:
    """验证对话ID格式"""
    if not conversation_id or not conversation_id.strip():
        return False, "对话ID不能为空"
    
    # 简单的UUID格式验证
    if len(conversation_id) < 10:
        return False, "对话ID格式无效"
    
    return True, None






