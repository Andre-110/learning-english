"""
日志工具 - 代理到结构化日志系统

所有旧接口保持兼容，自动使用新的结构化日志系统
"""
from services.utils.structured_logger import (
    get_logger,
    get_log_manager,
    set_user_context,
    get_user_context,
    log_user,
    log_perf,
    get_user_logs,
    search_logs,
    current_user_id,
    current_trace_id,
    UserContextFilter,
    JSONFormatter,
    HumanReadableFormatter,
    StructuredLogManager,
)
import logging
from typing import Optional, Dict, Any
import json
from datetime import datetime
import os


# ==================== 兼容旧接口 ====================

def set_current_user(user_id: str):
    """设置当前请求的用户标识（兼容旧接口）"""
    set_user_context(user_id)


def get_current_user() -> str:
    """获取当前请求的用户标识（兼容旧接口）"""
    user_id, _ = get_user_context()
    return user_id


def setup_logger(
    name: str = "lingua_coach", 
    level: str = "INFO",
    log_file: Optional[str] = None,
    detailed: bool = True
) -> logging.Logger:
    """
    设置日志器（兼容旧接口，使用新系统）
    """
    return get_log_manager().get_main_logger(name)


def log_module_io(
    logger: logging.Logger,
    module_name: str,
    function_name: str,
    inputs: Dict[str, Any],
    outputs: Optional[Dict[str, Any]] = None,
    level: str = "INFO"
):
    """
    记录模块的输入输出
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    input_str = json.dumps(inputs, ensure_ascii=False, indent=2)
    logger.log(log_level, f"[{module_name}.{function_name}] INPUT:\n{input_str}")
    
    if outputs is not None:
        output_str = json.dumps(outputs, ensure_ascii=False, indent=2, default=str)
        logger.log(log_level, f"[{module_name}.{function_name}] OUTPUT:\n{output_str}")


def log_user_interaction(
    logger: logging.Logger,
    conversation_id: str,
    user_id: str,
    user_input: str,
    system_output: Dict[str, Any],
    level: str = "INFO"
):
    """
    记录用户交互
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    logger.log(log_level, f"[USER_INTERACTION] Conversation: {conversation_id}, User: {user_id}")
    logger.log(log_level, f"[USER_INPUT] {user_input}")
    
    output_str = json.dumps(system_output, ensure_ascii=False, indent=2, default=str)
    logger.log(log_level, f"[SYSTEM_OUTPUT]\n{output_str}")


def create_test_logger(test_name: str, log_dir: str = "logs") -> logging.Logger:
    """
    创建测试专用的日志器
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = logging.getLogger(f"test_{test_name}_{timestamp}")
    logger.setLevel(logging.DEBUG)
    
    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)
    
    # 添加文件处理器
    log_file = os.path.join(log_dir, f"test_{test_name}_{timestamp}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)
    
    return logger
