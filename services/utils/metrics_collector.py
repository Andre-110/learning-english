"""
📈 业务指标采集器

功能：
1. 实时并发用户/连接数统计
2. 请求计数（QPS、成功率、错误率）
3. 延迟统计（P50、P90、P99）
4. 业务指标（对话数、消息数、TTS/ASR调用次数）
5. 自动聚合统计（分钟级、小时级、天级）
6. 历史数据持久化

使用方式：
    from services.utils.metrics_collector import metrics, record_request, record_latency
    
    # 记录请求
    record_request("api", "/ws/gpt4o-pipeline", success=True)
    
    # 记录延迟
    record_latency("tts", 1.5)  # 1.5秒
    
    # 获取当前指标
    metrics.get_current_metrics()
"""

import os
import json
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from collections import defaultdict
from dataclasses import dataclass, field, asdict
import logging
from logging.handlers import TimedRotatingFileHandler

# ==================== 数据结构 ====================

@dataclass
class ConnectionStats:
    """连接统计"""
    websocket_connections: int = 0          # 当前 WebSocket 连接数
    active_conversations: int = 0           # 活跃对话数
    unique_users: set = field(default_factory=set)  # 当前在线用户集合 (user_id)
    user_map: Dict[str, str] = field(default_factory=dict)  # user_id -> username 映射
    
    def to_dict(self) -> Dict:
        return {
            "websocket_connections": self.websocket_connections,
            "active_conversations": self.active_conversations,
            "online_users": len(self.unique_users),
            "user_list": list(self.unique_users),
            "user_map": self.user_map  # 🆕 暴露用户名映射
        }


@dataclass
class RequestStats:
    """请求统计"""
    total: int = 0
    success: int = 0
    failed: int = 0
    
    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 100.0
    
    def to_dict(self) -> Dict:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "success_rate": round(self.success_rate, 2)
        }


@dataclass 
class LatencyStats:
    """延迟统计"""
    samples: List[float] = field(default_factory=list)
    max_samples: int = 1000  # 最多保留1000个样本
    
    def add(self, latency_ms: float):
        self.samples.append(latency_ms)
        if len(self.samples) > self.max_samples:
            self.samples = self.samples[-self.max_samples:]
    
    def percentile(self, p: float) -> float:
        if not self.samples:
            return 0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * p / 100)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]
    
    def to_dict(self) -> Dict:
        if not self.samples:
            return {"count": 0, "avg": 0, "p50": 0, "p90": 0, "p99": 0, "max": 0}
        return {
            "count": len(self.samples),
            "avg": round(sum(self.samples) / len(self.samples), 2),
            "p50": round(self.percentile(50), 2),
            "p90": round(self.percentile(90), 2),
            "p99": round(self.percentile(99), 2),
            "max": round(max(self.samples), 2)
        }


# ==================== 主指标采集器 ====================

class MetricsCollector:
    """业务指标采集器"""
    
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
        
        # 连接统计
        self.connections = ConnectionStats()
        
        # 请求统计（按类型分）
        self.requests: Dict[str, RequestStats] = defaultdict(RequestStats)
        
        # 延迟统计（按操作分）
        self.latencies: Dict[str, LatencyStats] = defaultdict(LatencyStats)
        
        # 业务计数器
        self.counters: Dict[str, int] = defaultdict(int)
        
        # 时间窗口统计（用于计算 QPS）
        self._request_timestamps: List[float] = []
        self._window_size = 60  # 60秒窗口
        
        # 峰值记录
        self.peak_connections = 0
        self.peak_users = 0
        self.peak_qps = 0.0
        
        # 启动时间
        self.start_time = time.time()
        
        # 日志设置
        self._setup_logger()
        
        # 历史数据（分钟级聚合）
        self.history: List[Dict] = []
        self.max_history = 1440  # 保留24小时的分钟级数据
        
        # 启动后台聚合任务
        self._aggregation_thread = None
        self._running = False
        
        self._initialized = True
    
    def _setup_logger(self):
        """设置指标日志器"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        log_dir = os.path.join(base_dir, "online_logs", "metrics")
        os.makedirs(log_dir, exist_ok=True)
        
        self.logger = logging.getLogger("metrics")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.handlers.clear()
        
        log_file = os.path.join(log_dir, "metrics.log")
        file_handler = TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(message)s'))
        file_handler.suffix = "%Y-%m-%d"
        self.logger.addHandler(file_handler)
    
    # ==================== 连接管理 ====================
    
    def connection_opened(self, user_id: str = None, username: str = None, connection_type: str = "websocket"):
        """记录连接打开（实时写入日志）"""
        with self._lock:
            self.connections.websocket_connections += 1
            if user_id:
                self.connections.unique_users.add(user_id)
                # 🆕 存储用户名映射
                if username:
                    self.connections.user_map[user_id] = username
                elif user_id not in self.connections.user_map:
                    self.connections.user_map[user_id] = user_id[:8]  # 默认用 ID 前8位
            
            # 更新峰值
            if self.connections.websocket_connections > self.peak_connections:
                self.peak_connections = self.connections.websocket_connections
            if len(self.connections.unique_users) > self.peak_users:
                self.peak_users = len(self.connections.unique_users)
            
            self.counters["total_connections"] += 1
        
        # 🆕 实时写入日志
        try:
            from datetime import datetime, timezone
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "type": "connection",
                "action": "opened",
                "user_id": user_id,
                "username": username,  # 🆕 记录用户名
                "connection_type": connection_type,
                "current_connections": self.connections.websocket_connections,
                "online_users": len(self.connections.unique_users)
            }
            self.logger.info(json.dumps(log_entry, ensure_ascii=False))
        except Exception:
            pass
    
    def connection_closed(self, user_id: str = None):
        """记录连接关闭（实时写入日志）"""
        with self._lock:
            self.connections.websocket_connections = max(0, self.connections.websocket_connections - 1)
            # 🔧 修复：断开时清理用户（简化处理，假设每用户一个连接）
            if user_id and user_id in self.connections.unique_users:
                self.connections.unique_users.discard(user_id)
                self.connections.user_map.pop(user_id, None)
        
        # 🆕 实时写入日志
        try:
            from datetime import datetime, timezone
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "type": "connection",
                "action": "closed",
                "user_id": user_id,
                "current_connections": self.connections.websocket_connections,
                "online_users": len(self.connections.unique_users)
            }
            self.logger.info(json.dumps(log_entry, ensure_ascii=False))
        except Exception:
            pass
    
    def conversation_started(self, conversation_id: str = None):
        """记录对话开始（实时写入日志）"""
        with self._lock:
            self.connections.active_conversations += 1
            self.counters["total_conversations"] += 1
        
        # 🆕 实时写入日志
        try:
            from datetime import datetime, timezone
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "type": "conversation",
                "action": "started",
                "conversation_id": conversation_id,
                "active_conversations": self.connections.active_conversations
            }
            self.logger.info(json.dumps(log_entry, ensure_ascii=False))
        except Exception:
            pass
    
    def conversation_ended(self, conversation_id: str = None):
        """记录对话结束（实时写入日志）"""
        with self._lock:
            self.connections.active_conversations = max(0, self.connections.active_conversations - 1)
        
        # 🆕 实时写入日志
        try:
            from datetime import datetime, timezone
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "type": "conversation",
                "action": "ended",
                "conversation_id": conversation_id,
                "active_conversations": self.connections.active_conversations
            }
            self.logger.info(json.dumps(log_entry, ensure_ascii=False))
        except Exception:
            pass
    
    # ==================== 请求统计 ====================
    
    def record_request(self, category: str, endpoint: str = None, success: bool = True):
        """记录请求"""
        with self._lock:
            stats = self.requests[category]
            stats.total += 1
            if success:
                stats.success += 1
            else:
                stats.failed += 1
            
            # 记录时间戳用于 QPS 计算
            now = time.time()
            self._request_timestamps.append(now)
            
            # 清理过期时间戳
            cutoff = now - self._window_size
            self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
    
    def record_latency(self, operation: str, latency_ms: float):
        """记录延迟（实时写入日志）"""
        with self._lock:
            self.latencies[operation].add(latency_ms)
        
        # 🆕 实时写入到 metrics.log
        try:
            from datetime import datetime, timezone
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "type": "latency",
                "operation": operation,
                "latency_ms": round(latency_ms, 2)
            }
            self.logger.info(json.dumps(log_entry, ensure_ascii=False))
        except Exception:
            pass
    
    def increment_counter(self, name: str, value: int = 1):
        """增加计数器"""
        with self._lock:
            self.counters[name] += value
    
    # ==================== 指标获取 ====================
    
    def get_qps(self) -> float:
        """获取当前 QPS（每秒请求数）"""
        with self._lock:
            now = time.time()
            cutoff = now - self._window_size
            recent = [t for t in self._request_timestamps if t > cutoff]
            qps = len(recent) / self._window_size if self._window_size > 0 else 0
            
            if qps > self.peak_qps:
                self.peak_qps = qps
            
            return round(qps, 2)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前所有指标"""
        uptime = time.time() - self.start_time
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "uptime_seconds": int(uptime),
            "uptime_human": self._format_uptime(uptime),
            
            # 实时连接
            "connections": {
                "current": self.connections.to_dict(),
                "peak": {
                    "connections": self.peak_connections,
                    "users": self.peak_users
                }
            },
            
            # 请求统计
            "requests": {
                category: stats.to_dict() 
                for category, stats in self.requests.items()
            },
            
            # QPS
            "qps": {
                "current": self.get_qps(),
                "peak": round(self.peak_qps, 2)
            },
            
            # 延迟统计
            "latencies": {
                operation: stats.to_dict()
                for operation, stats in self.latencies.items()
            },
            
            # 业务计数器
            "counters": dict(self.counters)
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要（轻量级）"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "online_users": len(self.connections.unique_users),
            "active_connections": self.connections.websocket_connections,
            "active_conversations": self.connections.active_conversations,
            "qps": self.get_qps(),
            "total_conversations": self.counters.get("total_conversations", 0),
            "total_messages": self.counters.get("total_messages", 0)
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """格式化运行时间"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    # ==================== 历史数据 ====================
    
    def snapshot(self) -> Dict:
        """创建当前状态快照（包含系统资源）"""
        import psutil
        
        # 获取系统资源
        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "connections": self.connections.to_dict(),
            "qps": self.get_qps(),
            "requests": {k: v.to_dict() for k, v in self.requests.items()},
            "latencies": {k: v.to_dict() for k, v in self.latencies.items()},
            "counters": dict(self.counters),
            # 🆕 添加系统资源数据
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": mem.percent
            }
        }
        return snapshot
    
    def log_snapshot(self):
        """记录快照到日志"""
        snapshot = self.snapshot()
        self.logger.info(json.dumps(snapshot, ensure_ascii=False))
        
        # 保存到历史
        with self._lock:
            self.history.append(snapshot)
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
        
        return snapshot
    
    def get_history(self, minutes: int = 60) -> List[Dict]:
        """获取历史数据（优先从内存，不足从文件加载）"""
        with self._lock:
            # 如果请求的时间范围超过内存中的数据，从文件加载
            if minutes > len(self.history):
                return self._load_history_from_file(minutes)
            return self.history[-minutes:]
    
    def _load_history_from_file(self, minutes: int = 1440) -> List[Dict]:
        """从日志文件加载历史数据"""
        import glob
        from datetime import datetime, timedelta, timezone
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        log_dir = os.path.join(base_dir, "online_logs", "metrics")
        
        history_data = []
        
        # 计算需要加载的时间范围（使用 UTC 时间，因为日志是 UTC）
        now_utc = datetime.now(timezone.utc)
        start_time_utc = now_utc - timedelta(minutes=minutes)
        
        # 查找所有日志文件（今天和可能的历史文件）
        log_files = sorted(glob.glob(os.path.join(log_dir, "metrics.log*")))
        
        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            ts_str = record.get("timestamp", "")
                            if ts_str:
                                # 解析时间戳（UTC）
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                
                                # 过滤时间范围
                                if ts >= start_time_utc:
                                    history_data.append(record)
                        except (json.JSONDecodeError, ValueError):
                            continue
            except Exception as e:
                self.logger.warning(f"加载历史日志失败 {log_file}: {e}")
        
        # 按时间排序
        history_data.sort(key=lambda x: x.get("timestamp", ""))
        
        return history_data
    
    # ==================== 后台任务 ====================
    
    def start_aggregation(self, interval: int = 60):
        """启动后台聚合任务"""
        if self._running:
            return
        
        self._running = True
        
        def _aggregate_loop():
            while self._running:
                try:
                    self.log_snapshot()
                except Exception as e:
                    self.logger.error(f"聚合错误: {e}")
                time.sleep(interval)
        
        self._aggregation_thread = threading.Thread(target=_aggregate_loop, daemon=True)
        self._aggregation_thread.start()
    
    def stop_aggregation(self):
        """停止后台聚合"""
        self._running = False
        if self._aggregation_thread:
            self._aggregation_thread.join(timeout=5)
    
    # ==================== 告警检查 ====================
    
    def check_alerts(self) -> List[Dict]:
        """检查业务告警"""
        alerts = []
        
        # 高并发告警
        if self.connections.websocket_connections > 100:
            alerts.append({
                "level": "warning",
                "type": "high_concurrency",
                "message": f"并发连接数较高: {self.connections.websocket_connections}"
            })
        
        # 错误率告警
        for category, stats in self.requests.items():
            if stats.total > 10 and stats.success_rate < 95:
                alerts.append({
                    "level": "warning" if stats.success_rate >= 90 else "critical",
                    "type": "error_rate",
                    "message": f"{category} 成功率低: {stats.success_rate:.1f}%"
                })
        
        # 延迟告警
        for operation, stats in self.latencies.items():
            p99 = stats.percentile(99)
            if p99 > 5000:  # P99 > 5秒
                alerts.append({
                    "level": "warning",
                    "type": "high_latency",
                    "message": f"{operation} P99延迟过高: {p99:.0f}ms"
                })
        
        return alerts


# ==================== 全局单例和便捷函数 ====================

metrics = MetricsCollector()


def record_request(category: str, endpoint: str = None, success: bool = True):
    """记录请求"""
    metrics.record_request(category, endpoint, success)


def record_latency(operation: str, latency_ms: float):
    """记录延迟（毫秒）"""
    metrics.record_latency(operation, latency_ms)


def connection_opened(user_id: str = None, username: str = None):
    """记录连接打开"""
    metrics.connection_opened(user_id, username=username)


def connection_closed(user_id: str = None):
    """记录连接关闭"""
    metrics.connection_closed(user_id)


def conversation_started(conversation_id: str = None):
    """记录对话开始"""
    metrics.conversation_started(conversation_id)


def conversation_ended(conversation_id: str = None):
    """记录对话结束"""
    metrics.conversation_ended(conversation_id)


def increment(name: str, value: int = 1):
    """增加计数器"""
    metrics.increment_counter(name, value)


def get_metrics() -> Dict[str, Any]:
    """获取当前指标"""
    return metrics.get_current_metrics()


def get_metrics_summary() -> Dict[str, Any]:
    """获取指标摘要"""
    return metrics.get_summary()


if __name__ == "__main__":
    # 测试代码
    print("📈 业务指标采集器测试")
    print("=" * 50)
    
    # 模拟一些请求
    for i in range(10):
        record_request("api", "/test", success=i % 3 != 0)
        record_latency("llm", 500 + i * 100)
        record_latency("tts", 200 + i * 50)
    
    # 模拟连接
    connection_opened("user1")
    connection_opened("user2")
    connection_opened("user1")  # 同一用户多连接
    conversation_started("conv1")
    
    increment("total_messages", 5)
    
    # 打印指标
    import json
    print(json.dumps(get_metrics(), indent=2, ensure_ascii=False))
    
    print("\n⚠️ 告警检查:")
    alerts = metrics.check_alerts()
    for a in alerts:
        print(f"  [{a['level']}] {a['message']}")
