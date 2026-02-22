"""
⏱️ 统一时间轴事件日志模块

功能：
1. 记录每次对话的完整时间轴（12个关键时间点）
2. 支持前端和后端时间点的统一管理
3. 自动计算各环节延迟
4. 提供时间轴可视化数据

时间轴事件（12个关键点）：
1. client_speech_start   - 用户端开始说话时间（前端 VAD）
2. client_speech_end     - 用户端结束说话时间（前端 VAD）
3. server_audio_first    - 服务器端接收到第一帧音频
4. server_audio_last     - 服务器端接收到最后一帧音频
5. asr_start             - 开始 ASR 处理
6. asr_end               - ASR 处理完成
7. llm_start             - 开始 LLM 请求
8. llm_first_token       - LLM 返回首个 token
9. llm_end               - LLM 响应完成
10. tts_start            - 开始 TTS 处理
11. tts_first_chunk      - TTS 首块生成
12. tts_end              - TTS 处理完成
13. client_audio_first   - 用户端开始收到音频
14. client_audio_end     - 用户端音频播放结束

使用方式：
    from services.utils.timeline_logger import TimelineLogger, get_timeline_logger
    
    # 获取单例
    timeline = get_timeline_logger()
    
    # 记录事件
    timeline.record_event(
        user_id="user123",
        conversation_id="conv456",
        round_id=1,
        event_type="asr_start",
        timestamp_ms=1706860003100
    )
    
    # 获取完整时间轴
    events = timeline.get_round_timeline("user123", "conv456", 1)
    
    # 计算延迟
    latencies = timeline.calculate_latencies("user123", "conv456", 1)
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
class TimelineEvent:
    """单个时间轴事件"""
    event_type: str           # 事件类型
    timestamp_ms: int         # 毫秒级时间戳
    source: str = "server"    # 来源：server/client
    metadata: Dict = field(default_factory=dict)  # 额外元数据
    
    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type,
            "timestamp_ms": self.timestamp_ms,
            "source": self.source,
            "metadata": self.metadata
        }


@dataclass
class RoundTimeline:
    """一轮对话的完整时间轴"""
    user_id: str
    conversation_id: str
    round_id: int
    message_round_id: str
    events: Dict[str, TimelineEvent] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    
    def add_event(self, event_type: str, timestamp_ms: int, source: str = "server", metadata: Dict = None):
        """添加事件"""
        self.events[event_type] = TimelineEvent(
            event_type=event_type,
            timestamp_ms=timestamp_ms,
            source=source,
            metadata=metadata or {}
        )
    
    def get_event(self, event_type: str) -> Optional[TimelineEvent]:
        """获取事件"""
        return self.events.get(event_type)
    
    def calculate_latencies(self) -> Dict[str, int]:
        """计算各环节延迟（毫秒）"""
        latencies = {}
        
        # 网络延迟：用户说完 → 服务器收到
        if "client_speech_end" in self.events and "server_audio_last" in self.events:
            latencies["network_upload_ms"] = (
                self.events["server_audio_last"].timestamp_ms - 
                self.events["client_speech_end"].timestamp_ms
            )
        
        # ASR 延迟
        if "asr_start" in self.events and "asr_end" in self.events:
            latencies["asr_ms"] = (
                self.events["asr_end"].timestamp_ms - 
                self.events["asr_start"].timestamp_ms
            )
        
        # LLM TTFT（首 token 时间）
        if "llm_start" in self.events and "llm_first_token" in self.events:
            latencies["llm_ttft_ms"] = (
                self.events["llm_first_token"].timestamp_ms - 
                self.events["llm_start"].timestamp_ms
            )
        
        # LLM 总时间
        if "llm_start" in self.events and "llm_end" in self.events:
            latencies["llm_total_ms"] = (
                self.events["llm_end"].timestamp_ms - 
                self.events["llm_start"].timestamp_ms
            )
        
        # TTS 首块时间
        if "tts_start" in self.events and "tts_first_chunk" in self.events:
            latencies["tts_first_chunk_ms"] = (
                self.events["tts_first_chunk"].timestamp_ms - 
                self.events["tts_start"].timestamp_ms
            )
        
        # TTS 总时间
        if "tts_start" in self.events and "tts_end" in self.events:
            latencies["tts_total_ms"] = (
                self.events["tts_end"].timestamp_ms - 
                self.events["tts_start"].timestamp_ms
            )
        
        # 网络下行延迟：服务器发出 → 用户收到
        if "tts_first_chunk" in self.events and "client_audio_first" in self.events:
            latencies["network_download_ms"] = (
                self.events["client_audio_first"].timestamp_ms - 
                self.events["tts_first_chunk"].timestamp_ms
            )
        
        # 用户感知延迟（核心指标）：用户说完 → 听到 AI 回复
        if "client_speech_end" in self.events and "client_audio_first" in self.events:
            latencies["user_perceived_ms"] = (
                self.events["client_audio_first"].timestamp_ms - 
                self.events["client_speech_end"].timestamp_ms
            )
        
        # 用户说话时长
        if "client_speech_start" in self.events and "client_speech_end" in self.events:
            latencies["user_speech_duration_ms"] = (
                self.events["client_speech_end"].timestamp_ms - 
                self.events["client_speech_start"].timestamp_ms
            )
        
        # AI 回复时长
        if "client_audio_first" in self.events and "client_audio_end" in self.events:
            latencies["ai_audio_duration_ms"] = (
                self.events["client_audio_end"].timestamp_ms - 
                self.events["client_audio_first"].timestamp_ms
            )
        
        # 端到端时间：用户开始说话 → AI 说完
        if "client_speech_start" in self.events and "client_audio_end" in self.events:
            latencies["e2e_total_ms"] = (
                self.events["client_audio_end"].timestamp_ms - 
                self.events["client_speech_start"].timestamp_ms
            )
        
        return latencies
    
    def to_dict(self) -> Dict:
        """转为字典格式"""
        return {
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "round_id": self.round_id,
            "message_round_id": self.message_round_id,
            "events": {k: v.to_dict() for k, v in self.events.items()},
            "latencies": self.calculate_latencies(),
            "created_at": self.created_at
        }


# ==================== 时间轴日志器 ====================

class TimelineLogger:
    """时间轴事件日志器"""
    
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
        
        # 内存缓存：{(user_id, conv_id, round_id): RoundTimeline}
        self._timelines: Dict[tuple, RoundTimeline] = {}
        self._timelines_lock = threading.Lock()
        
        # 设置日志目录
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.log_dir = os.path.join(base_dir, "online_logs", "timeline")
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 设置专用日志器
        self.logger = self._setup_logger()
        
        # 历史缓存（最近的时间轴，用于快速查询）
        self._history: List[RoundTimeline] = []
        self._max_history = 1000
        self._load_history_from_log()
        
        self._initialized = True
    
    def _setup_logger(self) -> logging.Logger:
        """设置时间轴日志器"""
        logger = logging.getLogger("timeline")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()
        
        # 时间轴日志文件（按天轮转，保留30天）
        log_file = os.path.join(self.log_dir, "timeline.log")
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
    
    def _load_history_from_log(self) -> None:
        """从 timeline.log 回放历史轮次（仅 round_complete）"""
        log_file = os.path.join(self.log_dir, "timeline.log")
        if not os.path.exists(log_file):
            return
        
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    if entry.get("type") != "round_complete":
                        continue
                    
                    user_id = entry.get("user_id", "anonymous")
                    conversation_id = entry.get("conversation_id", "unknown")
                    round_id = entry.get("round_id", 0)
                    message_round_id = entry.get("message_round_id") or f"{conversation_id}_{round_id}"
                    
                    timeline = RoundTimeline(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        round_id=round_id,
                        message_round_id=message_round_id
                    )
                    
                    events = entry.get("events") or {}
                    for event_type, ev in events.items():
                        try:
                            timestamp_ms = int(ev.get("timestamp_ms", 0))
                        except Exception:
                            timestamp_ms = 0
                        if timestamp_ms <= 0:
                            continue
                        timeline.events[event_type] = TimelineEvent(
                            event_type=event_type,
                            timestamp_ms=timestamp_ms,
                            source=ev.get("source", "server"),
                            metadata=ev.get("metadata") or {}
                        )
                    
                    created_at = entry.get("created_at")
                    if isinstance(created_at, int):
                        timeline.created_at = created_at
                    
                    self._history.append(timeline)
        except Exception:
            # 回放失败不影响主流程
            return
        
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
    
    def _get_key(self, user_id: str, conversation_id: str, round_id: int) -> tuple:
        """生成缓存键"""
        return (user_id or "anonymous", conversation_id or "unknown", round_id)
    
    def _get_or_create_timeline(
        self, 
        user_id: str, 
        conversation_id: str, 
        round_id: int,
        message_round_id: str = None
    ) -> RoundTimeline:
        """获取或创建时间轴"""
        key = self._get_key(user_id, conversation_id, round_id)
        
        with self._timelines_lock:
            if key not in self._timelines:
                self._timelines[key] = RoundTimeline(
                    user_id=user_id or "anonymous",
                    conversation_id=conversation_id or "unknown",
                    round_id=round_id,
                    message_round_id=message_round_id or f"{conversation_id}_{round_id}"
                )
            return self._timelines[key]
    
    def record_event(
        self,
        user_id: str,
        conversation_id: str,
        round_id: int,
        event_type: str,
        timestamp_ms: int = None,
        source: str = "server",
        message_round_id: str = None,
        metadata: Dict = None
    ):
        """
        记录时间轴事件（实时写入日志）
        
        Args:
            user_id: 用户 ID
            conversation_id: 对话 ID
            round_id: 轮次 ID（从 1 开始）
            event_type: 事件类型
            timestamp_ms: 毫秒级时间戳（默认为当前时间）
            source: 来源（server/client）
            message_round_id: 消息轮次 ID
            metadata: 额外元数据
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
        
        timeline = self._get_or_create_timeline(
            user_id, conversation_id, round_id, message_round_id
        )
        timeline.add_event(event_type, timestamp_ms, source, metadata)
        
        # 🆕 实时写入日志（不等 finalize_round）
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "type": "event",
                "user_id": user_id,
                "conversation_id": conversation_id,
                "round_id": round_id,
                "message_round_id": message_round_id,
                "event_type": event_type,
                "event_timestamp_ms": timestamp_ms,
                "source": source,
                "metadata": metadata
            }
            self.logger.info(json.dumps(log_entry, ensure_ascii=False))
        except Exception as e:
            # 日志写入失败不影响主流程
            pass
    
    def record_client_event(
        self,
        user_id: str,
        conversation_id: str,
        round_id: int,
        event_type: str,
        timestamp_ms: int,
        message_round_id: str = None,
        metadata: Dict = None
    ):
        """记录来自客户端的事件"""
        self.record_event(
            user_id=user_id,
            conversation_id=conversation_id,
            round_id=round_id,
            event_type=event_type,
            timestamp_ms=timestamp_ms,
            source="client",
            message_round_id=message_round_id,
            metadata=metadata
        )
    
    def get_round_timeline(
        self, 
        user_id: str, 
        conversation_id: str, 
        round_id: int
    ) -> Optional[RoundTimeline]:
        """获取指定轮次的时间轴"""
        key = self._get_key(user_id, conversation_id, round_id)
        with self._timelines_lock:
            return self._timelines.get(key)
    
    def finalize_round(
        self, 
        user_id: str, 
        conversation_id: str, 
        round_id: int
    ) -> Optional[Dict]:
        """
        结束一轮对话，记录到日志并返回完整数据
        
        这个方法应该在一轮对话完全结束后调用（AI 播放完毕）
        """
        key = self._get_key(user_id, conversation_id, round_id)
        
        with self._timelines_lock:
            timeline = self._timelines.pop(key, None)
        
        if timeline is None:
            return None
        
        # 转为字典
        data = timeline.to_dict()
        
        # 记录到日志
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "type": "round_complete",
            **data
        }
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))
        
        # 保存到历史
        self._history.append(timeline)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        return data
    
    def get_latencies(
        self, 
        user_id: str, 
        conversation_id: str, 
        round_id: int
    ) -> Dict[str, int]:
        """获取指定轮次的延迟数据"""
        timeline = self.get_round_timeline(user_id, conversation_id, round_id)
        if timeline:
            return timeline.calculate_latencies()
        return {}
    
    def get_recent_timelines(self, count: int = 100) -> List[Dict]:
        """获取最近的时间轴数据"""
        return [t.to_dict() for t in self._history[-count:]]
    
    def get_user_timelines(self, user_id: str, count: int = 50) -> List[Dict]:
        """获取指定用户的时间轴数据"""
        user_timelines = [t for t in self._history if t.user_id == user_id]
        return [t.to_dict() for t in user_timelines[-count:]]
    
    def get_conversation_timelines(self, conversation_id: str) -> List[Dict]:
        """获取指定对话的所有时间轴数据"""
        conv_timelines = [t for t in self._history if t.conversation_id == conversation_id]
        return [t.to_dict() for t in conv_timelines]
    
    def get_stats(self) -> Dict:
        """获取时间轴统计信息"""
        if not self._history:
            return {"count": 0}
        
        # 收集所有延迟数据
        all_latencies = defaultdict(list)
        for timeline in self._history:
            latencies = timeline.calculate_latencies()
            for key, value in latencies.items():
                if value > 0:  # 只统计有效值
                    all_latencies[key].append(value)
        
        # 计算统计值
        stats = {"count": len(self._history)}
        for key, values in all_latencies.items():
            if values:
                sorted_vals = sorted(values)
                n = len(sorted_vals)
                stats[key] = {
                    "avg": int(sum(values) / n),
                    "min": sorted_vals[0],
                    "max": sorted_vals[-1],
                    "p50": sorted_vals[n // 2],
                    "p90": sorted_vals[int(n * 0.9)],
                    "p99": sorted_vals[int(n * 0.99)] if n >= 100 else sorted_vals[-1],
                    "count": n
                }
        
        return stats


# ==================== 便捷函数 ====================

_timeline_logger: Optional[TimelineLogger] = None


def get_timeline_logger() -> TimelineLogger:
    """获取时间轴日志器单例"""
    global _timeline_logger
    if _timeline_logger is None:
        _timeline_logger = TimelineLogger()
    return _timeline_logger


def record_timeline_event(
    user_id: str,
    conversation_id: str,
    round_id: int,
    event_type: str,
    timestamp_ms: int = None,
    source: str = "server",
    message_round_id: str = None,
    metadata: Dict = None
):
    """记录时间轴事件（便捷函数）"""
    get_timeline_logger().record_event(
        user_id=user_id,
        conversation_id=conversation_id,
        round_id=round_id,
        event_type=event_type,
        timestamp_ms=timestamp_ms,
        source=source,
        message_round_id=message_round_id,
        metadata=metadata
    )


def finalize_round_timeline(
    user_id: str,
    conversation_id: str,
    round_id: int
) -> Optional[Dict]:
    """结束一轮对话的时间轴记录"""
    return get_timeline_logger().finalize_round(user_id, conversation_id, round_id)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    import time
    
    print("⏱️ 时间轴日志模块测试")
    print("=" * 60)
    
    logger = get_timeline_logger()
    
    # 模拟一轮对话
    user_id = "test_user"
    conv_id = "test_conv"
    round_id = 1
    
    base_time = int(time.time() * 1000)
    
    # 记录事件
    events = [
        ("client_speech_start", 0, "client"),
        ("client_speech_end", 2000, "client"),
        ("server_audio_first", 50, "server"),
        ("server_audio_last", 2100, "server"),
        ("asr_start", 2100, "server"),
        ("asr_end", 2500, "server"),
        ("llm_start", 2500, "server"),
        ("llm_first_token", 3000, "server"),
        ("llm_end", 4000, "server"),
        ("tts_start", 2800, "server"),
        ("tts_first_chunk", 3200, "server"),
        ("tts_end", 5000, "server"),
        ("client_audio_first", 3300, "client"),
        ("client_audio_end", 6000, "client"),
    ]
    
    for event_type, offset, source in events:
        logger.record_event(
            user_id=user_id,
            conversation_id=conv_id,
            round_id=round_id,
            event_type=event_type,
            timestamp_ms=base_time + offset,
            source=source
        )
    
    # 获取时间轴
    timeline = logger.get_round_timeline(user_id, conv_id, round_id)
    print(f"\n📊 事件数: {len(timeline.events)}")
    
    # 计算延迟
    latencies = timeline.calculate_latencies()
    print(f"\n⏱️ 延迟统计:")
    for key, value in latencies.items():
        print(f"   {key}: {value}ms")
    
    # 结束轮次
    data = logger.finalize_round(user_id, conv_id, round_id)
    print(f"\n✅ 轮次已结束，日志已记录")
    
    # 统计信息
    stats = logger.get_stats()
    print(f"\n📈 统计信息:")
    print(json.dumps(stats, indent=2))
