"""
提示词管理模块 - GPT-4o Pipeline 精简版

🆕 2026-02-01 精简：只导出核心函数
"""
from .templates import (
    get_pipeline_system_prompt,
    get_pipeline_system_prompt_with_memory,
    get_pipeline_user_prompt,
    get_pipeline_user_prompt_with_memory,
    get_pipeline_initial_prompt,
    get_pipeline_initial_prompt_with_content,
    get_content_injection_prompt,
    get_interest_extraction_prompt,
    # 兼容层
    get_rhythm_instruction,
    analyze_conversation_rhythm,
)

__all__ = [
    "get_pipeline_system_prompt",
    "get_pipeline_system_prompt_with_memory",
    "get_pipeline_user_prompt",
    "get_pipeline_user_prompt_with_memory",
    "get_pipeline_initial_prompt",
    "get_pipeline_initial_prompt_with_content",
    "get_content_injection_prompt",
    "get_interest_extraction_prompt",
    "get_rhythm_instruction",
    "analyze_conversation_rhythm",
]
