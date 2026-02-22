"""
🖥️ 系统服务器监测模块

功能：
1. CPU 使用率监测
2. 内存使用监测
3. 磁盘空间监测
4. 网络 I/O 监测
5. 进程资源监测
6. 系统负载监测

使用方式：
    from services.utils.system_monitor import SystemMonitor, start_system_monitor
    
    # 启动后台监测（每60秒记录一次）
    monitor = start_system_monitor(interval=60)
    
    # 手动获取当前状态
    status = monitor.get_current_status()
    
    # 停止监测
    monitor.stop()
"""

import os
import json
import time
import asyncio
import threading
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from logging.handlers import TimedRotatingFileHandler

import psutil


class SystemMonitor:
    """系统资源监测器"""
    
    def __init__(self, log_dir: str = None, interval: int = 60):
        """
        初始化系统监测器
        
        Args:
            log_dir: 日志目录，默认为 logs/system/
            interval: 监测间隔（秒），默认60秒
        """
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._async_task: Optional[asyncio.Task] = None
        
        # 设置日志目录
        if log_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            log_dir = os.path.join(base_dir, "online_logs", "system")
        
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 设置专用日志器
        self.logger = self._setup_logger()
        
        # 记录初始网络计数器（用于计算增量）
        self._last_net_io = psutil.net_io_counters()
        self._last_disk_io = psutil.disk_io_counters()
        self._last_time = time.time()
        
        # 获取进程对象
        self.process = psutil.Process()
    
    def _setup_logger(self) -> logging.Logger:
        """设置系统监测日志器"""
        logger = logging.getLogger("system_monitor")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()
        
        # 系统状态日志文件（按天轮转，保留30天）
        log_file = os.path.join(self.log_dir, "system.log")
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
        logger.addHandler(file_handler)
        
        return logger
    
    def get_cpu_info(self) -> Dict[str, Any]:
        """获取 CPU 信息"""
        return {
            "percent": psutil.cpu_percent(interval=0.1),
            "percent_per_cpu": psutil.cpu_percent(interval=0.1, percpu=True),
            "count_logical": psutil.cpu_count(logical=True),
            "count_physical": psutil.cpu_count(logical=False),
            "load_avg": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
        }
    
    def get_memory_info(self) -> Dict[str, Any]:
        """获取内存信息"""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent,
            "swap_total_gb": round(swap.total / (1024**3), 2),
            "swap_used_gb": round(swap.used / (1024**3), 2),
            "swap_percent": swap.percent
        }
    
    def get_disk_info(self) -> Dict[str, Any]:
        """获取磁盘信息"""
        disk = psutil.disk_usage('/')
        
        # 计算磁盘 I/O 速率
        current_io = psutil.disk_io_counters()
        current_time = time.time()
        time_delta = current_time - self._last_time
        
        if time_delta > 0 and self._last_disk_io:
            read_speed = (current_io.read_bytes - self._last_disk_io.read_bytes) / time_delta
            write_speed = (current_io.write_bytes - self._last_disk_io.write_bytes) / time_delta
        else:
            read_speed = 0
            write_speed = 0
        
        return {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": disk.percent,
            "read_speed_mb_s": round(read_speed / (1024**2), 2),
            "write_speed_mb_s": round(write_speed / (1024**2), 2)
        }
    
    def get_network_info(self) -> Dict[str, Any]:
        """获取网络信息"""
        current_io = psutil.net_io_counters()
        current_time = time.time()
        time_delta = current_time - self._last_time
        
        if time_delta > 0:
            bytes_sent_speed = (current_io.bytes_sent - self._last_net_io.bytes_sent) / time_delta
            bytes_recv_speed = (current_io.bytes_recv - self._last_net_io.bytes_recv) / time_delta
        else:
            bytes_sent_speed = 0
            bytes_recv_speed = 0
        
        # 更新计数器
        self._last_net_io = current_io
        self._last_disk_io = psutil.disk_io_counters()
        self._last_time = current_time
        
        return {
            "bytes_sent_total_mb": round(current_io.bytes_sent / (1024**2), 2),
            "bytes_recv_total_mb": round(current_io.bytes_recv / (1024**2), 2),
            "send_speed_kb_s": round(bytes_sent_speed / 1024, 2),
            "recv_speed_kb_s": round(bytes_recv_speed / 1024, 2),
            "packets_sent": current_io.packets_sent,
            "packets_recv": current_io.packets_recv,
            "errin": current_io.errin,
            "errout": current_io.errout
        }
    
    def get_process_info(self) -> Dict[str, Any]:
        """获取当前进程信息"""
        try:
            with self.process.oneshot():
                return {
                    "pid": self.process.pid,
                    "cpu_percent": self.process.cpu_percent(),
                    "memory_percent": round(self.process.memory_percent(), 2),
                    "memory_rss_mb": round(self.process.memory_info().rss / (1024**2), 2),
                    "memory_vms_mb": round(self.process.memory_info().vms / (1024**2), 2),
                    "num_threads": self.process.num_threads(),
                    "num_fds": self.process.num_fds() if hasattr(self.process, 'num_fds') else None,
                    "open_files": len(self.process.open_files()),
                    "connections": len(self.process.net_connections())
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"error": "无法获取进程信息"}
    
    def get_current_status(self) -> Dict[str, Any]:
        """获取当前系统状态（完整）"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "cpu": self.get_cpu_info(),
            "memory": self.get_memory_info(),
            "disk": self.get_disk_info(),
            "network": self.get_network_info(),
            "process": self.get_process_info()
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """获取系统状态摘要（轻量级）"""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        try:
            proc_mem = round(self.process.memory_percent(), 2)
            proc_cpu = self.process.cpu_percent()
        except:
            proc_mem = 0
            proc_cpu = 0
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "cpu_percent": cpu_percent,
            "memory_percent": mem.percent,
            "disk_percent": disk.percent,
            "process_memory_percent": proc_mem,
            "process_cpu_percent": proc_cpu,
            "load_avg": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
        }
    
    def log_status(self):
        """记录当前系统状态到日志"""
        status = self.get_current_status()
        self.logger.info(json.dumps(status, ensure_ascii=False))
        return status
    
    def _monitor_loop(self):
        """同步监测循环（用于线程）"""
        while self._running:
            try:
                self.log_status()
            except Exception as e:
                self.logger.error(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "error": str(e)
                }))
            time.sleep(self.interval)
    
    async def _async_monitor_loop(self):
        """异步监测循环"""
        while self._running:
            try:
                self.log_status()
            except Exception as e:
                self.logger.error(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "error": str(e)
                }))
            await asyncio.sleep(self.interval)
    
    def start(self, use_thread: bool = True):
        """
        启动后台监测
        
        Args:
            use_thread: True 使用线程，False 使用 asyncio 任务
        """
        if self._running:
            return
        
        self._running = True
        
        # 记录启动日志
        startup_info = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": "monitor_started",
            "interval_seconds": self.interval,
            "initial_status": self.get_summary()
        }
        self.logger.info(json.dumps(startup_info, ensure_ascii=False))
        
        if use_thread:
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
        else:
            # 获取当前事件循环或创建新的
            try:
                loop = asyncio.get_running_loop()
                self._async_task = loop.create_task(self._async_monitor_loop())
            except RuntimeError:
                # 没有运行中的事件循环，使用线程
                self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
                self._thread.start()
    
    def stop(self):
        """停止后台监测"""
        self._running = False
        
        # 记录停止日志
        stop_info = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": "monitor_stopped",
            "final_status": self.get_summary()
        }
        self.logger.info(json.dumps(stop_info, ensure_ascii=False))
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        
        if self._async_task and not self._async_task.done():
            self._async_task.cancel()
    
    def check_alerts(self) -> list:
        """检查是否有告警条件"""
        alerts = []
        summary = self.get_summary()
        
        # CPU 告警阈值
        if summary["cpu_percent"] > 90:
            alerts.append({
                "level": "critical",
                "type": "cpu",
                "message": f"CPU 使用率过高: {summary['cpu_percent']}%"
            })
        elif summary["cpu_percent"] > 75:
            alerts.append({
                "level": "warning",
                "type": "cpu",
                "message": f"CPU 使用率较高: {summary['cpu_percent']}%"
            })
        
        # 内存告警阈值
        if summary["memory_percent"] > 90:
            alerts.append({
                "level": "critical",
                "type": "memory",
                "message": f"内存使用率过高: {summary['memory_percent']}%"
            })
        elif summary["memory_percent"] > 80:
            alerts.append({
                "level": "warning",
                "type": "memory",
                "message": f"内存使用率较高: {summary['memory_percent']}%"
            })
        
        # 磁盘告警阈值
        if summary["disk_percent"] > 95:
            alerts.append({
                "level": "critical",
                "type": "disk",
                "message": f"磁盘空间不足: {summary['disk_percent']}%"
            })
        elif summary["disk_percent"] > 85:
            alerts.append({
                "level": "warning",
                "type": "disk",
                "message": f"磁盘空间较低: {summary['disk_percent']}%"
            })
        
        return alerts


# ==================== 便捷函数 ====================

_monitor_instance: Optional[SystemMonitor] = None


def get_system_monitor() -> SystemMonitor:
    """获取系统监测器单例"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SystemMonitor()
    return _monitor_instance


def start_system_monitor(interval: int = 60) -> SystemMonitor:
    """
    启动系统监测（便捷函数）
    
    Args:
        interval: 监测间隔（秒）
    
    Returns:
        SystemMonitor 实例
    """
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SystemMonitor(interval=interval)
    _monitor_instance.start()
    return _monitor_instance


def stop_system_monitor():
    """停止系统监测"""
    global _monitor_instance
    if _monitor_instance:
        _monitor_instance.stop()


def get_system_status() -> Dict[str, Any]:
    """获取当前系统状态（便捷函数）"""
    return get_system_monitor().get_current_status()


def get_system_summary() -> Dict[str, Any]:
    """获取系统状态摘要（便捷函数）"""
    return get_system_monitor().get_summary()


if __name__ == "__main__":
    # 测试代码
    print("🖥️ 系统监测模块测试")
    print("=" * 50)
    
    monitor = SystemMonitor()
    status = monitor.get_current_status()
    
    print(f"\n📊 CPU 信息:")
    print(f"   使用率: {status['cpu']['percent']}%")
    print(f"   逻辑核心: {status['cpu']['count_logical']}")
    print(f"   负载均值: {status['cpu']['load_avg']}")
    
    print(f"\n💾 内存信息:")
    print(f"   总计: {status['memory']['total_gb']} GB")
    print(f"   已用: {status['memory']['used_gb']} GB ({status['memory']['percent']}%)")
    print(f"   可用: {status['memory']['available_gb']} GB")
    
    print(f"\n💿 磁盘信息:")
    print(f"   总计: {status['disk']['total_gb']} GB")
    print(f"   已用: {status['disk']['used_gb']} GB ({status['disk']['percent']}%)")
    print(f"   可用: {status['disk']['free_gb']} GB")
    
    print(f"\n🌐 网络信息:")
    print(f"   发送: {status['network']['bytes_sent_total_mb']} MB")
    print(f"   接收: {status['network']['bytes_recv_total_mb']} MB")
    
    print(f"\n⚙️ 进程信息:")
    print(f"   PID: {status['process']['pid']}")
    print(f"   内存: {status['process']['memory_rss_mb']} MB")
    print(f"   线程数: {status['process']['num_threads']}")
    
    # 检查告警
    alerts = monitor.check_alerts()
    if alerts:
        print(f"\n⚠️ 告警:")
        for alert in alerts:
            print(f"   [{alert['level']}] {alert['message']}")
    else:
        print(f"\n✅ 系统状态正常")
