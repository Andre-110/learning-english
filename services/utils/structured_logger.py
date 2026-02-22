"""
🆕 结构化日志系统 - 线上服务规范的日志管理

特性：
1. 按用户分文件（可选）
2. 按天轮转
3. JSON 结构化格式（方便 ELK/Loki）
4. 用户追踪（user_id 贯穿请求链路）
5. 性能日志单独文件
"""
import logging
import os
import json
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from contextvars import ContextVar
from logging.handlers import TimedRotatingFileHandler
import threading

# ==================== 上下文变量 ====================
# 线程/协程安全的用户标识
current_user_id: ContextVar[str] = ContextVar('current_user_id', default='anonymous')
current_trace_id: ContextVar[str] = ContextVar('current_trace_id', default='')


def set_user_context(user_id: str, trace_id: str = None):
    """设置当前请求的用户上下文"""
    current_user_id.set(user_id or 'anonymous')
    if trace_id:
        current_trace_id.set(trace_id)
    else:
        # 自动生成 trace_id
        import uuid
        current_trace_id.set(str(uuid.uuid4())[:8])


def get_user_context() -> tuple:
    """获取当前请求的用户上下文"""
    return current_user_id.get(), current_trace_id.get()


# ==================== 结构化日志格式化器 ====================
class JSONFormatter(logging.Formatter):
    """JSON 格式化器 - 方便 ELK/Loki 检索"""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "user_id": getattr(record, 'user_id', current_user_id.get()),
            "trace_id": getattr(record, 'trace_id', current_trace_id.get()),
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        
        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_data["data"] = record.extra_data
            
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data, ensure_ascii=False)


class UserContextFilter(logging.Filter):
    """自动添加用户上下文到日志记录"""
    
    def filter(self, record):
        record.user_id = current_user_id.get()
        record.trace_id = current_trace_id.get()
        return True


class HumanReadableFormatter(logging.Formatter):
    """人类可读格式（控制台/调试用）"""
    
    def format(self, record):
        user_id = getattr(record, 'user_id', current_user_id.get())
        trace_id = getattr(record, 'trace_id', current_trace_id.get())
        
        # 用户标识只取前8字符
        user_short = user_id[:8] if len(user_id) > 8 else user_id
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return f"{timestamp} | {record.levelname:<8} | [{user_short}:{trace_id}] {record.getMessage()}"


# ==================== 日志管理器 ====================
class StructuredLogManager:
    """结构化日志管理器 - 支持分用户/分级别/分天"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        # 旧目录（应用运行日志，保留用于开发调试）
        self.log_dir = os.path.join(base_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 🆕 线上日志目录（生产监控）
        self.online_log_dir = os.path.join(base_dir, "online_logs")
        os.makedirs(self.online_log_dir, exist_ok=True)
        
        # 用户专属日志目录 → online_logs/users/
        self.user_log_dir = os.path.join(self.online_log_dir, "users")
        os.makedirs(self.user_log_dir, exist_ok=True)
        
        # 性能日志目录 → online_logs/performance/
        self.perf_log_dir = os.path.join(self.online_log_dir, "performance")
        os.makedirs(self.perf_log_dir, exist_ok=True)
        
        # 🆕 后端日志目录 → online_logs/backend/
        self.backend_log_dir = os.path.join(self.online_log_dir, "backend")
        os.makedirs(self.backend_log_dir, exist_ok=True)
        
        # 🆕 前端日志目录 → online_logs/frontend/
        self.frontend_log_dir = os.path.join(self.online_log_dir, "frontend")
        os.makedirs(self.frontend_log_dir, exist_ok=True)
        
        self._loggers = {}
        self._user_handlers = {}
        self._initialized = True
    
    def get_main_logger(self, name: str = "lingua_coach") -> logging.Logger:
        """获取主日志器（所有日志）"""
        if name in self._loggers:
            return self._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        
        # 清除已有 handlers
        logger.handlers.clear()
        
        # 添加用户上下文过滤器
        logger.addFilter(UserContextFilter())
        
        # 1. 控制台输出（人类可读格式）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(HumanReadableFormatter())
        logger.addHandler(console_handler)
        
        # 2. 主日志文件（按天轮转，保留7天）
        main_log = os.path.join(self.log_dir, "app.log")
        file_handler = TimedRotatingFileHandler(
            main_log,
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JSONFormatter())
        file_handler.suffix = "%Y-%m-%d"
        logger.addHandler(file_handler)
        
        # 3. 错误日志文件（只记录 ERROR 及以上）
        error_log = os.path.join(self.log_dir, "error.log")
        error_handler = TimedRotatingFileHandler(
            error_log,
            when='midnight',
            interval=1,
            backupCount=30,  # 错误日志保留30天
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        error_handler.suffix = "%Y-%m-%d"
        logger.addHandler(error_handler)
        
        # 4. 🆕 线上后端日志（online_logs/backend/app.log）
        backend_log = os.path.join(self.backend_log_dir, "app.log")
        backend_handler = TimedRotatingFileHandler(
            backend_log,
            when='midnight',
            interval=1,
            backupCount=30,  # 保留30天
            encoding='utf-8'
        )
        backend_handler.setLevel(logging.INFO)  # 只记录 INFO 及以上
        backend_handler.setFormatter(JSONFormatter())
        backend_handler.suffix = "%Y-%m-%d"
        logger.addHandler(backend_handler)
        
        # 5. 🆕 线上错误日志（online_logs/errors/error.log）
        online_error_dir = os.path.join(self.online_log_dir, "errors")
        os.makedirs(online_error_dir, exist_ok=True)
        online_error_log = os.path.join(online_error_dir, "error.log")
        online_error_handler = TimedRotatingFileHandler(
            online_error_log,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        online_error_handler.setLevel(logging.ERROR)
        online_error_handler.setFormatter(JSONFormatter())
        online_error_handler.suffix = "%Y-%m-%d"
        logger.addHandler(online_error_handler)
        
        self._loggers[name] = logger
        return logger
    
    def get_user_logger(self, user_id: str) -> logging.Logger:
        """获取用户专属日志器"""
        if not user_id or user_id == 'anonymous':
            return self.get_main_logger()
        
        logger_name = f"user.{user_id[:8]}"
        
        if logger_name in self._loggers:
            return self._loggers[logger_name]
        
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers.clear()
        logger.addFilter(UserContextFilter())
        
        # 用户专属日志文件（按天轮转）
        user_log = os.path.join(self.user_log_dir, f"{user_id[:8]}.log")
        file_handler = TimedRotatingFileHandler(
            user_log,
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JSONFormatter())
        file_handler.suffix = "%Y-%m-%d"
        logger.addHandler(file_handler)
        
        self._loggers[logger_name] = logger
        return logger
    
    def get_perf_logger(self) -> logging.Logger:
        """获取性能日志器"""
        logger_name = "performance"
        
        if logger_name in self._loggers:
            return self._loggers[logger_name]
        
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()
        logger.addFilter(UserContextFilter())
        
        # 性能日志文件
        perf_log = os.path.join(self.perf_log_dir, "latency.log")
        file_handler = TimedRotatingFileHandler(
            perf_log,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(JSONFormatter())
        file_handler.suffix = "%Y-%m-%d"
        logger.addHandler(file_handler)
        
        self._loggers[logger_name] = logger
        return logger
    
    def log_to_user(self, user_id: str, level: int, message: str, **extra):
        """同时记录到主日志和用户日志"""
        main_logger = self.get_main_logger()
        
        # 创建带额外数据的日志记录
        if extra:
            main_logger.log(level, message, extra={'extra_data': extra})
        else:
            main_logger.log(level, message)
        
        # 用户专属日志
        if user_id and user_id != 'anonymous':
            user_logger = self.get_user_logger(user_id)
            if extra:
                user_logger.log(level, message, extra={'extra_data': extra})
            else:
                user_logger.log(level, message)
    
    def log_latency(self, user_id: str, operation: str, latency_ms: float, **extra):
        """记录性能指标"""
        perf_logger = self.get_perf_logger()
        
        data = {
            "operation": operation,
            "latency_ms": latency_ms,
            "user_id": user_id,
            **extra
        }
        
        perf_logger.info(f"{operation}: {latency_ms:.0f}ms", extra={'extra_data': data})


# ==================== 便捷函数 ====================
_log_manager = None


def get_log_manager() -> StructuredLogManager:
    """获取日志管理器单例"""
    global _log_manager
    if _log_manager is None:
        _log_manager = StructuredLogManager()
    return _log_manager


def get_logger(name: str = "lingua_coach") -> logging.Logger:
    """获取主日志器（兼容旧接口）"""
    return get_log_manager().get_main_logger(name)


def log_user(user_id: str, level: str, message: str, **extra):
    """记录用户相关日志"""
    level_num = getattr(logging, level.upper(), logging.INFO)
    get_log_manager().log_to_user(user_id, level_num, message, **extra)


def log_perf(user_id: str, operation: str, latency_ms: float, **extra):
    """记录性能指标"""
    get_log_manager().log_latency(user_id, operation, latency_ms, **extra)


# ==================== 用户日志查看工具 ====================
def get_user_logs(user_id: str, lines: int = 100) -> list:
    """获取用户最近的日志"""
    manager = get_log_manager()
    user_log = os.path.join(manager.user_log_dir, f"{user_id[:8]}.log")
    
    if not os.path.exists(user_log):
        return []
    
    logs = []
    with open(user_log, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except:
                pass
    
    return logs[-lines:]


def search_logs(user_id: str = None, level: str = None, keyword: str = None, 
                start_time: str = None, end_time: str = None) -> list:
    """搜索日志"""
    manager = get_log_manager()
    
    # 确定搜索的文件
    if user_id:
        log_file = os.path.join(manager.user_log_dir, f"{user_id[:8]}.log")
    else:
        log_file = os.path.join(manager.log_dir, "app.log")
    
    if not os.path.exists(log_file):
        return []
    
    results = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                log = json.loads(line)
                
                # 过滤条件
                if level and log.get('level') != level.upper():
                    continue
                if keyword and keyword.lower() not in log.get('message', '').lower():
                    continue
                if start_time and log.get('timestamp', '') < start_time:
                    continue
                if end_time and log.get('timestamp', '') > end_time:
                    continue
                
                results.append(log)
            except:
                pass
    
    return results
