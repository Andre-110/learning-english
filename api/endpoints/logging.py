"""
📊 前端日志上报端点

功能：
1. 前端日志上报（HTTP POST，WebSocket 断开时的兜底）
2. 时间轴事件上报
3. 批量日志上报
4. 获取时间轴统计

使用方式：
    POST /api/logs/frontend    - 上报前端日志
    POST /api/logs/timeline    - 上报时间轴事件
    POST /api/logs/batch       - 批量上报日志
    GET  /api/logs/timeline/stats - 获取时间轴统计
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import time

from services.utils.structured_logger import get_logger
from services.utils.timeline_logger import (
    get_timeline_logger,
    record_timeline_event,
    finalize_round_timeline
)
from services.utils.metrics_collector import record_latency

router = APIRouter(prefix="/api/logs", tags=["logging"])
logger = get_logger("api.logging")


# ==================== 请求模型 ====================

class FrontendLogRequest(BaseModel):
    """前端日志请求"""
    level: str = "info"  # info, warning, error, anomaly
    log_type: str = "unknown"
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[int] = None  # 毫秒时间戳
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None


class TimelineEventRequest(BaseModel):
    """时间轴事件请求"""
    event_type: str  # client_speech_start, client_speech_end, etc.
    timestamp_ms: int  # 毫秒时间戳
    user_id: str
    conversation_id: str
    round_id: int
    message_round_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BatchLogRequest(BaseModel):
    """批量日志请求"""
    logs: List[FrontendLogRequest]
    timeline_events: Optional[List[TimelineEventRequest]] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None


class UserPerceivedLatencyRequest(BaseModel):
    """用户感知延迟上报"""
    latency_ms: int
    vad_silence_time: int  # 前端 VAD 检测到静默的时间戳
    first_audio_time: int  # 前端收到首块音频的时间戳
    user_id: str
    conversation_id: str
    message_round_id: Optional[str] = None


# ==================== 端点 ====================

@router.post("/frontend")
async def report_frontend_log(request: FrontendLogRequest):
    """
    上报前端日志
    
    用于 WebSocket 断开时的兜底，或需要持久化的关键日志
    """
    try:
        timestamp = request.timestamp or int(time.time() * 1000)
        
        # 根据级别选择日志方法
        if request.level == "anomaly" or request.level == "error":
            logger.warning(
                f"[前端-HTTP] 🚨 {request.log_type}: {request.message} | "
                f"user={request.user_id}, conv={request.conversation_id}, "
                f"data={request.data}"
            )
        else:
            logger.info(
                f"[前端-HTTP] [{request.log_type}] {request.message} | "
                f"user={request.user_id}, conv={request.conversation_id}"
            )
        
        return {
            "success": True,
            "timestamp": timestamp,
            "server_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"[前端日志] 处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/timeline")
async def report_timeline_event(request: TimelineEventRequest):
    """
    上报时间轴事件
    
    前端上报关键时间点：
    - client_speech_start: 用户开始说话
    - client_speech_end: 用户结束说话  
    - client_audio_first: 用户端开始收到音频
    - client_audio_end: 用户端音频播放结束
    """
    try:
        record_timeline_event(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            round_id=request.round_id,
            event_type=request.event_type,
            timestamp_ms=request.timestamp_ms,
            source="client",
            message_round_id=request.message_round_id,
            metadata=request.metadata
        )
        
        logger.debug(
            f"[时间轴-HTTP] {request.event_type} @ {request.timestamp_ms} | "
            f"user={request.user_id}, round={request.round_id}"
        )
        
        return {
            "success": True,
            "event_type": request.event_type,
            "timestamp_ms": request.timestamp_ms,
            "server_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"[时间轴] 处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def report_batch_logs(request: BatchLogRequest):
    """
    批量上报日志和时间轴事件
    
    用于 WebSocket 断开后一次性上报缓存的日志
    """
    try:
        processed_logs = 0
        processed_events = 0
        
        # 处理日志
        for log in request.logs:
            user_id = log.user_id or request.user_id
            conv_id = log.conversation_id or request.conversation_id
            
            if log.level in ["anomaly", "error"]:
                logger.warning(f"[前端-批量] 🚨 {log.log_type}: {log.message}")
            else:
                logger.info(f"[前端-批量] [{log.log_type}] {log.message}")
            processed_logs += 1
        
        # 处理时间轴事件
        if request.timeline_events:
            for event in request.timeline_events:
                record_timeline_event(
                    user_id=event.user_id,
                    conversation_id=event.conversation_id,
                    round_id=event.round_id,
                    event_type=event.event_type,
                    timestamp_ms=event.timestamp_ms,
                    source="client",
                    message_round_id=event.message_round_id,
                    metadata=event.metadata
                )
                processed_events += 1
        
        logger.info(f"[批量日志] 处理完成: {processed_logs} 条日志, {processed_events} 条时间轴事件")
        
        return {
            "success": True,
            "processed_logs": processed_logs,
            "processed_events": processed_events,
            "server_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"[批量日志] 处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/latency")
async def report_user_perceived_latency(request: UserPerceivedLatencyRequest):
    """
    上报用户感知延迟
    
    用户感知延迟 = 用户说完话 → AI 开始发出声音
    """
    try:
        # 记录到 metrics
        record_latency("user_perceived", request.latency_ms)
        
        logger.info(
            f"📊 [用户感知延迟-HTTP] {request.latency_ms}ms | "
            f"user={request.user_id}, conv={request.conversation_id}, "
            f"round={request.message_round_id}"
        )
        
        return {
            "success": True,
            "latency_ms": request.latency_ms,
            "server_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"[延迟上报] 处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline/stats")
async def get_timeline_stats():
    """
    获取时间轴统计信息
    
    返回各环节延迟的统计数据（P50、P90、P99、avg、max）
    """
    try:
        timeline_logger = get_timeline_logger()
        stats = timeline_logger.get_stats()
        
        return {
            "success": True,
            "stats": stats,
            "server_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"[时间轴统计] 获取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline/recent")
async def get_recent_timelines(
    count: int = Query(default=50, ge=1, le=500),
    user_id: Optional[str] = Query(None)  # 🆕 支持按用户筛选
):
    """
    获取最近的时间轴数据
    
    用于调试和可视化
    """
    try:
        timeline_logger = get_timeline_logger()
        
        if user_id:
            # 如果指定了 user_id，使用 get_user_timelines
            timelines = timeline_logger.get_user_timelines(user_id, count)
        else:
            timelines = timeline_logger.get_recent_timelines(count)
        
        return {
            "success": True,
            "count": len(timelines),
            "timelines": timelines,
            "server_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"[时间轴历史] 获取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline/user/{user_id}")
async def get_user_timelines(
    user_id: str,
    count: int = Query(default=50, ge=1, le=200)
):
    """
    获取指定用户的时间轴数据
    """
    try:
        timeline_logger = get_timeline_logger()
        timelines = timeline_logger.get_user_timelines(user_id, count)
        
        return {
            "success": True,
            "user_id": user_id,
            "count": len(timelines),
            "timelines": timelines,
            "server_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"[用户时间轴] 获取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline/conversation/{conversation_id}")
async def get_conversation_timelines(conversation_id: str):
    """
    获取指定对话的所有时间轴数据
    """
    try:
        timeline_logger = get_timeline_logger()
        timelines = timeline_logger.get_conversation_timelines(conversation_id)
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "count": len(timelines),
            "timelines": timelines,
            "server_time": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"[对话时间轴] 获取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
