"""
🔍 日志索引器 - 统一检索线上问题

功能：
1. 自动索引所有日志文件
2. 按 user_id / conversation_id / timestamp 快速检索
3. 关联同一请求的所有日志（跨文件）
4. 导出问题报告

使用方式：
    from services.utils.log_indexer import LogIndexer, search_logs
    
    # 按用户检索
    logs = search_logs(user_id="user123")
    
    # 按对话检索
    logs = search_logs(conversation_id="conv456")
    
    # 按时间范围检索
    logs = search_logs(start_time="2024-02-01 10:00", end_time="2024-02-01 11:00")
    
    # 按错误类型检索
    logs = search_logs(level="ERROR")
"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Generator
from pathlib import Path
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: datetime
    level: str
    source: str  # 来源文件
    message: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    round_id: Optional[int] = None
    raw_data: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "source": self.source,
            "message": self.message[:200],  # 截断长消息
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "round_id": self.round_id
        }


class LogIndexer:
    """日志索引器"""
    
    def __init__(self, logs_dir: str = None):
        if logs_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            logs_dir = os.path.join(base_dir, "online_logs")
        self.logs_dir = logs_dir
        
        # 日志文件列表（online_logs 目录结构）
        self.log_files = {
            # 系统日志
            "system": "system/system.log",
            # 业务指标
            "metrics": "metrics/metrics.log",
            # 时间轴（每轮对话）
            "timeline": "timeline/timeline.log",
            # 前端上报
            "frontend": "frontend/frontend.log",
            # 后端日志
            "backend": "backend/backend.log",
            # 性能日志
            "performance": "performance/performance.log",
        }
        
        # 兼容旧的 logs/ 目录（应用日志仍在那里）
        self.legacy_log_files = {
            "app": "../logs/app.log",
            "error": "../logs/error.log",
            "server": "../logs/server.log",
        }
    
    def search(
        self,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        round_id: Optional[int] = None,
        level: Optional[str] = None,  # INFO, WARNING, ERROR
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keyword: Optional[str] = None,
        sources: Optional[List[str]] = None,  # 指定搜索的日志文件
        limit: int = 100
    ) -> List[LogEntry]:
        """
        统一检索日志
        
        Args:
            user_id: 用户ID
            conversation_id: 对话ID
            round_id: 轮次ID
            level: 日志级别
            start_time: 开始时间
            end_time: 结束时间
            keyword: 关键词
            sources: 日志来源（app, error, server, system, metrics, timeline）
            limit: 最大返回条数
            
        Returns:
            匹配的日志条目列表
        """
        results = []
        # 合并新旧日志文件列表
        all_files = {**self.log_files, **self.legacy_log_files}
        sources = sources or list(all_files.keys())
        
        for source in sources:
            if source not in all_files:
                continue
            
            log_path = os.path.join(self.logs_dir, all_files[source])
            if not os.path.exists(log_path):
                continue
            
            for entry in self._parse_log_file(log_path, source):
                if self._matches(entry, user_id, conversation_id, round_id, 
                               level, start_time, end_time, keyword):
                    results.append(entry)
                    if len(results) >= limit:
                        break
            
            if len(results) >= limit:
                break
        
        # 按时间排序
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:limit]
    
    def _parse_log_file(self, log_path: str, source: str) -> Generator[LogEntry, None, None]:
        """解析日志文件"""
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    entry = self._parse_line(line, source)
                    if entry:
                        yield entry
        except Exception as e:
            logger.warning(f"解析日志文件失败 {log_path}: {e}")
    
    def _parse_line(self, line: str, source: str) -> Optional[LogEntry]:
        """解析单行日志"""
        try:
            # JSON 格式日志
            if line.startswith('{'):
                data = json.loads(line)
                return LogEntry(
                    timestamp=self._parse_timestamp(data.get('timestamp', '')),
                    level=data.get('level', 'INFO'),
                    source=source,
                    message=data.get('message', ''),
                    user_id=data.get('user_id') or self._extract_field(data.get('message', ''), 'user_id'),
                    conversation_id=data.get('conversation_id') or self._extract_field(data.get('message', ''), 'conversation_id'),
                    round_id=data.get('round_id'),
                    raw_data=data
                )
            
            # 文本格式日志（server.log）
            # 格式: 2024-02-01 10:00:00 | module | LEVEL | message
            match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*([^|]+)\s*\|\s*(\w+)\s*\|\s*(.*)', line)
            if match:
                return LogEntry(
                    timestamp=datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S'),
                    level=match.group(3).strip(),
                    source=source,
                    message=match.group(4).strip(),
                    user_id=self._extract_field(match.group(4), 'user_id'),
                    conversation_id=self._extract_field(match.group(4), 'conversation_id'),
                    raw_data={"raw": line}
                )
            
            return None
        except Exception:
            return None
    
    def _parse_timestamp(self, ts: str) -> datetime:
        """解析时间戳"""
        if not ts:
            return datetime.now()
        
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue
        
        return datetime.now()
    
    def _extract_field(self, text: str, field: str) -> Optional[str]:
        """从文本中提取字段"""
        patterns = {
            'user_id': r'user_id[=:]\s*([a-zA-Z0-9_-]+)',
            'conversation_id': r'conversation_id[=:]\s*([a-zA-Z0-9_-]+)',
        }
        
        if field in patterns:
            match = re.search(patterns[field], text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def _matches(
        self, 
        entry: LogEntry,
        user_id: Optional[str],
        conversation_id: Optional[str],
        round_id: Optional[int],
        level: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        keyword: Optional[str]
    ) -> bool:
        """检查是否匹配条件"""
        if user_id and entry.user_id != user_id:
            return False
        if conversation_id and entry.conversation_id != conversation_id:
            return False
        if round_id is not None and entry.round_id != round_id:
            return False
        if level and entry.level.upper() != level.upper():
            return False
        if start_time and entry.timestamp < start_time:
            return False
        if end_time and entry.timestamp > end_time:
            return False
        if keyword and keyword.lower() not in entry.message.lower():
            return False
        return True
    
    def get_user_timeline(self, user_id: str, hours: int = 24) -> List[LogEntry]:
        """获取用户最近的完整时间线"""
        start_time = datetime.now() - timedelta(hours=hours)
        return self.search(user_id=user_id, start_time=start_time, limit=500)
    
    def get_error_report(self, hours: int = 24) -> Dict[str, Any]:
        """获取错误报告"""
        start_time = datetime.now() - timedelta(hours=hours)
        errors = self.search(level="ERROR", start_time=start_time, limit=1000)
        
        # 按错误类型分组
        error_types = {}
        for entry in errors:
            # 提取错误类型（从消息中）
            error_type = "Unknown"
            if "ASR" in entry.message:
                error_type = "ASR Error"
            elif "LLM" in entry.message:
                error_type = "LLM Error"
            elif "TTS" in entry.message:
                error_type = "TTS Error"
            elif "WebSocket" in entry.message:
                error_type = "WebSocket Error"
            elif "Memory" in entry.message:
                error_type = "Memory Error"
            
            if error_type not in error_types:
                error_types[error_type] = []
            error_types[error_type].append(entry.to_dict())
        
        return {
            "time_range": {
                "start": start_time.isoformat(),
                "end": datetime.now().isoformat()
            },
            "total_errors": len(errors),
            "by_type": {k: len(v) for k, v in error_types.items()},
            "samples": {k: v[:5] for k, v in error_types.items()}  # 每类最多5个样本
        }
    
    def export_incident_report(
        self, 
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """导出问题报告（用于排查线上问题）"""
        logs = self.search(
            user_id=user_id,
            conversation_id=conversation_id,
            start_time=start_time,
            end_time=end_time,
            limit=1000
        )
        
        return {
            "query": {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None
            },
            "total_logs": len(logs),
            "log_levels": {
                "ERROR": len([l for l in logs if l.level == "ERROR"]),
                "WARNING": len([l for l in logs if l.level == "WARNING"]),
                "INFO": len([l for l in logs if l.level == "INFO"]),
            },
            "timeline": [l.to_dict() for l in logs]
        }


# 单例
_indexer: Optional[LogIndexer] = None


def get_log_indexer() -> LogIndexer:
    """获取日志索引器单例"""
    global _indexer
    if _indexer is None:
        _indexer = LogIndexer()
    return _indexer


def search_logs(**kwargs) -> List[LogEntry]:
    """快捷搜索接口"""
    return get_log_indexer().search(**kwargs)


def get_error_report(hours: int = 24) -> Dict[str, Any]:
    """获取错误报告"""
    return get_log_indexer().get_error_report(hours)


def export_incident_report(**kwargs) -> Dict[str, Any]:
    """导出问题报告"""
    return get_log_indexer().export_incident_report(**kwargs)
