"""
📊 监控仪表盘 API 端点

提供系统状态、业务指标、告警信息的统一接口
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from services.utils.system_monitor import get_system_monitor, get_system_status, get_system_summary
from services.utils.metrics_collector import metrics, get_metrics, get_metrics_summary
from services.utils.structured_logger import get_logger

logger = get_logger("api.monitoring")
router = APIRouter(prefix="/monitoring", tags=["monitoring"])


# ==================== 数据模型 ====================

class AlertConfig(BaseModel):
    """告警配置"""
    webhook_url: Optional[str] = Field(None, description="Webhook 通知 URL")
    enabled: bool = Field(True, description="是否启用告警")


class Alert(BaseModel):
    """告警信息"""
    level: str
    type: str
    message: str
    timestamp: Optional[str] = None


# ==================== 全局告警配置 ====================
_alert_config = AlertConfig()
_alert_history: List[Dict] = []
MAX_ALERT_HISTORY = 100


# ==================== API 端点 ====================

@router.get("/dashboard")
async def get_dashboard():
    """
    获取完整监控仪表盘数据
    
    包含：系统状态 + 业务指标 + 告警
    """
    try:
        system_monitor = get_system_monitor()
        
        return {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            
            # 系统状态
            "system": system_monitor.get_current_status(),
            
            # 业务指标
            "metrics": get_metrics(),
            
            # 告警
            "alerts": {
                "system": system_monitor.check_alerts(),
                "business": metrics.check_alerts(),
                "recent": _alert_history[-10:]  # 最近10条告警
            }
        }
    except Exception as e:
        logger.error(f"获取监控数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_monitoring_summary():
    """
    获取监控摘要（轻量级，适合频繁轮询）
    """
    try:
        system_summary = get_system_summary()
        metrics_summary = get_metrics_summary()
        
        # 合并告警
        system_monitor = get_system_monitor()
        all_alerts = system_monitor.check_alerts() + metrics.check_alerts()
        
        return {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            
            # 系统摘要
            "cpu_percent": system_summary.get("cpu_percent", 0),
            "memory_percent": system_summary.get("memory_percent", 0),
            "disk_percent": system_summary.get("disk_percent", 0),
            
            # 业务摘要
            "online_users": metrics_summary.get("online_users", 0),
            "active_connections": metrics_summary.get("active_connections", 0),
            "qps": metrics_summary.get("qps", 0),
            "total_conversations": metrics_summary.get("total_conversations", 0),
            
            # 告警数
            "alert_count": len(all_alerts),
            "has_critical": any(a.get("level") == "critical" for a in all_alerts)
        }
    except Exception as e:
        logger.error(f"获取监控摘要失败: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/system")
async def get_system_details():
    """获取详细系统状态"""
    try:
        return {
            "status": "ok",
            **get_system_status()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/metrics")
async def get_business_metrics():
    """获取业务指标"""
    try:
        return {
            "status": "ok",
            **get_metrics()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/metrics/history")
async def get_metrics_history(
    minutes: int = 60,
    hours: int = 0,
    downsample: bool = True
):
    """
    获取历史指标数据（用于图表）
    
    参数：
    - minutes: 获取最近 N 分钟的数据（默认 60）
    - hours: 获取最近 N 小时的数据（会覆盖 minutes 参数）
    - downsample: 是否降采样（超过 120 个点时自动降采样，避免前端卡顿）
    
    示例：
    - /metrics/history?minutes=30      → 最近 30 分钟
    - /metrics/history?hours=6         → 最近 6 小时
    - /metrics/history?hours=24        → 最近 24 小时
    """
    try:
        # 计算总分钟数
        total_minutes = hours * 60 if hours > 0 else minutes
        
        # 限制最大查询范围（7天）
        total_minutes = min(total_minutes, 7 * 24 * 60)
        
        history = metrics.get_history(total_minutes)
        
        # 降采样：如果数据点太多，按间隔取样
        if downsample and len(history) > 120:
            step = len(history) // 120
            history = history[::step]
        
        return {
            "status": "ok",
            "count": len(history),
            "requested_minutes": total_minutes,
            "data": history
        }
    except Exception as e:
        logger.error(f"获取历史数据失败: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/alerts")
async def get_alerts():
    """获取当前告警"""
    try:
        system_monitor = get_system_monitor()
        system_alerts = system_monitor.check_alerts()
        business_alerts = metrics.check_alerts()
        
        return {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "system_alerts": system_alerts,
            "business_alerts": business_alerts,
            "total": len(system_alerts) + len(business_alerts),
            "history": _alert_history[-20:]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/alerts/config")
async def get_alert_config():
    """获取告警配置"""
    return {
        "enabled": _alert_config.enabled,
        "webhook_configured": bool(_alert_config.webhook_url)
    }


@router.post("/alerts/config")
async def set_alert_config(config: AlertConfig):
    """设置告警配置"""
    global _alert_config
    _alert_config = config
    logger.info(f"告警配置已更新: enabled={config.enabled}, webhook={bool(config.webhook_url)}")
    return {"status": "ok", "message": "配置已更新"}


@router.post("/alerts/test")
async def test_alert():
    """测试告警通知"""
    import httpx
    
    if not _alert_config.webhook_url:
        return {"status": "error", "message": "未配置 Webhook URL"}
    
    try:
        test_alert = {
            "level": "info",
            "type": "test",
            "message": "这是一条测试告警",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "LinguaCoach Monitor"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                _alert_config.webhook_url,
                json=test_alert,
                timeout=10
            )
            
            if response.status_code == 200:
                return {"status": "ok", "message": "测试告警已发送"}
            else:
                return {"status": "error", "message": f"Webhook 返回: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ==================== 告警推送函数 ====================

async def send_alert(alert: Dict):
    """发送告警通知"""
    global _alert_history
    
    # 添加时间戳
    alert["timestamp"] = datetime.utcnow().isoformat() + "Z"
    
    # 记录到历史
    _alert_history.append(alert)
    if len(_alert_history) > MAX_ALERT_HISTORY:
        _alert_history = _alert_history[-MAX_ALERT_HISTORY:]
    
    # 记录到日志
    logger.warning(f"[告警] [{alert.get('level')}] {alert.get('type')}: {alert.get('message')}")
    
    # 发送 Webhook（如果配置了）
    if _alert_config.enabled and _alert_config.webhook_url:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    _alert_config.webhook_url,
                    json={
                        **alert,
                        "source": "LinguaCoach Monitor"
                    },
                    timeout=5
                )
        except Exception as e:
            logger.error(f"发送告警失败: {e}")


# ==================== 后台告警检查任务 ====================

import asyncio

_alert_check_task = None
_alert_check_running = False


async def _alert_check_loop():
    """后台告警检查循环"""
    global _alert_check_running
    _alert_check_running = True
    
    while _alert_check_running:
        try:
            # 检查系统告警
            system_monitor = get_system_monitor()
            system_alerts = system_monitor.check_alerts()
            
            # 检查业务告警
            business_alerts = metrics.check_alerts()
            
            # 发送新告警
            for alert in system_alerts + business_alerts:
                # 去重：检查最近是否已发送过相同类型的告警
                recent_types = [a.get("type") for a in _alert_history[-10:]]
                if alert.get("type") not in recent_types:
                    await send_alert(alert)
        
        except Exception as e:
            logger.error(f"告警检查失败: {e}")
        
        await asyncio.sleep(60)  # 每分钟检查一次


def start_alert_check():
    """启动后台告警检查"""
    global _alert_check_task
    
    if _alert_check_task is None:
        try:
            loop = asyncio.get_running_loop()
            _alert_check_task = loop.create_task(_alert_check_loop())
            logger.info("后台告警检查已启动")
        except RuntimeError:
            # 没有运行中的事件循环，稍后启动
            pass


def stop_alert_check():
    """停止后台告警检查"""
    global _alert_check_running, _alert_check_task
    _alert_check_running = False
    if _alert_check_task:
        _alert_check_task.cancel()
        _alert_check_task = None
