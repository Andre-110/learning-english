"""
连接监控服务 - 心跳检测 + 不活动监控

功能：
1. 心跳检测：定期检查连接是否存活
2. 不活动监控：长时间无活动时发送警告或断开
3. 异常事件记录：记录连接异常供排查

参考：UserGenie OpenAI Voice Client 的心跳机制
"""
import time
import asyncio
from typing import Optional, Callable, Any, List, Dict
from dataclasses import dataclass, field
from fastapi import WebSocket

from services.utils.logger import get_logger

logger = get_logger("services.connection_monitor")


@dataclass
class AnomalyEvent:
    """异常事件"""
    type: str
    message: str
    timestamp: float = field(default_factory=time.time)
    data: Optional[Dict[str, Any]] = None


class ConnectionMonitor:
    """
    连接监控器
    
    使用方式：
        monitor = ConnectionMonitor(websocket, session_id)
        
        # 启动监控
        await monitor.start()
        
        # 在消息处理中更新活动时间
        monitor.update_activity()
        
        # 记录异常
        monitor.record_anomaly("ERROR_TYPE", "描述")
        
        # 停止监控
        await monitor.stop()
    """
    
    # 心跳间隔：10 秒
    HEARTBEAT_INTERVAL_SECONDS = 10
    
    # 心跳超时：5 分钟
    HEARTBEAT_TIMEOUT_SECONDS = 5 * 60
    
    # 不活动警告阈值：2 分钟
    INACTIVITY_WARNING_SECONDS = 2 * 60
    
    # 不活动断开阈值：5 分钟
    INACTIVITY_DISCONNECT_SECONDS = 5 * 60
    
    # 不活动检查间隔：30 秒
    INACTIVITY_CHECK_INTERVAL_SECONDS = 30
    
    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        on_heartbeat_timeout: Optional[Callable] = None,
        on_inactivity_warning: Optional[Callable] = None,
        on_inactivity_disconnect: Optional[Callable] = None,
    ):
        self.websocket = websocket
        self.session_id = session_id
        
        # 回调函数
        self.on_heartbeat_timeout = on_heartbeat_timeout
        self.on_inactivity_warning = on_inactivity_warning
        self.on_inactivity_disconnect = on_inactivity_disconnect
        
        # 状态
        self.last_pong_time: float = time.time()
        self.last_activity_time: float = time.time()
        self.start_time: float = time.time()
        self.is_running: bool = False
        
        # 任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._inactivity_task: Optional[asyncio.Task] = None
        
        # 异常记录
        self.anomaly_events: List[AnomalyEvent] = []
        self._max_anomaly_events = 100
    
    async def start(self):
        """启动监控"""
        if self.is_running:
            return
        
        self.is_running = True
        self.start_time = time.time()
        self.last_pong_time = time.time()
        self.last_activity_time = time.time()
        
        # 启动心跳任务
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # 启动不活动检测任务
        self._inactivity_task = asyncio.create_task(self._inactivity_loop())
        
        logger.info(f"[Monitor] 连接监控已启动: {self.session_id}")
    
    async def stop(self):
        """停止监控"""
        self.is_running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        
        if self._inactivity_task:
            self._inactivity_task.cancel()
            try:
                await self._inactivity_task
            except asyncio.CancelledError:
                pass
            self._inactivity_task = None
        
        logger.info(f"[Monitor] 连接监控已停止: {self.session_id}")
    
    def update_activity(self):
        """更新活动时间（在收到消息时调用）"""
        self.last_activity_time = time.time()
    
    def update_pong(self):
        """更新 pong 时间（在收到 pong 时调用）"""
        self.last_pong_time = time.time()
    
    def record_anomaly(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
        """记录异常事件"""
        event = AnomalyEvent(
            type=event_type,
            message=message,
            timestamp=time.time(),
            data=data
        )
        
        self.anomaly_events.append(event)
        
        # 限制数量
        if len(self.anomaly_events) > self._max_anomaly_events:
            self.anomaly_events = self.anomaly_events[-self._max_anomaly_events:]
        
        # 记录日志
        logger.warning(f"[Anomaly][{self.session_id}][{event_type}] {message}")
        if data:
            logger.warning(f"[Anomaly][{self.session_id}][{event_type}] Data: {data}")
    
    def get_health(self) -> Dict[str, Any]:
        """获取连接健康状态"""
        now = time.time()
        return {
            "session_id": self.session_id,
            "is_running": self.is_running,
            "duration": now - self.start_time,
            "last_activity_ago": now - self.last_activity_time,
            "last_pong_ago": now - self.last_pong_time,
            "anomaly_count": len(self.anomaly_events),
            "recent_anomalies": [
                {"type": e.type, "message": e.message, "timestamp": e.timestamp}
                for e in self.anomaly_events[-10:]
            ]
        }
    
    async def _heartbeat_loop(self):
        """心跳检测循环"""
        while self.is_running:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)
            
            if not self.is_running:
                break
            
            now = time.time()
            
            # 检查心跳超时
            time_since_pong = now - self.last_pong_time
            if time_since_pong > self.HEARTBEAT_TIMEOUT_SECONDS:
                self.record_anomaly(
                    "HEARTBEAT_TIMEOUT",
                    f"No pong for {time_since_pong:.1f}s",
                    {"timeout": self.HEARTBEAT_TIMEOUT_SECONDS}
                )
                
                if self.on_heartbeat_timeout:
                    try:
                        await self.on_heartbeat_timeout()
                    except Exception as e:
                        logger.error(f"[Monitor] 心跳超时回调失败: {e}")
                
                # 不主动断开，让上层决定
                continue
            
            # 发送 ping（前端需要响应 pong）
            # 注意：这里不发送 ping，因为前端主动发送 ping，后端响应 pong
            # 如果需要服务端主动 ping，可以取消下面的注释
            # try:
            #     await self.websocket.send_json({
            #         "type": "ping",
            #         "timestamp": now
            #     })
            # except Exception as e:
            #     self.record_anomaly("PING_SEND_FAILED", str(e))
    
    async def _inactivity_loop(self):
        """不活动检测循环"""
        warning_sent = False
        
        while self.is_running:
            await asyncio.sleep(self.INACTIVITY_CHECK_INTERVAL_SECONDS)
            
            if not self.is_running:
                break
            
            now = time.time()
            inactive_time = now - self.last_activity_time
            
            # 检查是否超过警告阈值
            if inactive_time > self.INACTIVITY_WARNING_SECONDS and not warning_sent:
                warning_sent = True
                
                logger.warning(f"[Monitor] 不活动警告: {self.session_id}, {inactive_time:.1f}s")
                
                try:
                    await self.websocket.send_json({
                        "type": "inactivity_warning",
                        "duration": inactive_time,
                        "message": f"No activity for {int(inactive_time)} seconds"
                    })
                except Exception as e:
                    self.record_anomaly("INACTIVITY_WARNING_SEND_FAILED", str(e))
                
                if self.on_inactivity_warning:
                    try:
                        await self.on_inactivity_warning(inactive_time)
                    except Exception as e:
                        logger.error(f"[Monitor] 不活动警告回调失败: {e}")
            
            # 检查是否超过断开阈值
            if inactive_time > self.INACTIVITY_DISCONNECT_SECONDS:
                self.record_anomaly(
                    "INACTIVITY_DISCONNECT",
                    f"No activity for {inactive_time:.1f}s, disconnecting",
                    {"threshold": self.INACTIVITY_DISCONNECT_SECONDS}
                )
                
                try:
                    await self.websocket.send_json({
                        "type": "inactivity_disconnect",
                        "duration": inactive_time,
                        "message": "Session terminated due to inactivity"
                    })
                except Exception:
                    pass
                
                if self.on_inactivity_disconnect:
                    try:
                        await self.on_inactivity_disconnect(inactive_time)
                    except Exception as e:
                        logger.error(f"[Monitor] 不活动断开回调失败: {e}")
                
                # 停止监控
                self.is_running = False
                break
            
            # 如果活动恢复，重置警告状态
            if inactive_time < self.INACTIVITY_WARNING_SECONDS:
                warning_sent = False
