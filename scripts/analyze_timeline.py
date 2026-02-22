#!/usr/bin/env python3
"""
⏱️ 完整时间轴分析脚本

功能：
1. 解析 timeline.log 日志文件
2. 展示每轮对话的完整时间轴
3. 计算各环节延迟统计（P50/P90/P99）
4. 生成可视化报告

使用方式：
    python scripts/analyze_timeline.py              # 分析最近1天
    python scripts/analyze_timeline.py --days 3    # 分析最近3天
    python scripts/analyze_timeline.py --user xxx  # 分析指定用户
    python scripts/analyze_timeline.py --conv xxx  # 分析指定对话
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

TIMELINE_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "timeline", "timeline.log")


def load_timeline_logs(
    start_date: datetime = None,
    end_date: datetime = None,
    user_id: str = None,
    conversation_id: str = None
) -> List[Dict]:
    """加载时间轴日志"""
    
    if not os.path.exists(TIMELINE_LOG_FILE):
        print(f"❌ 时间轴日志文件不存在: {TIMELINE_LOG_FILE}")
        return []
    
    timelines = []
    
    with open(TIMELINE_LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                
                # 过滤：只处理 round_complete 类型
                if data.get("type") != "round_complete":
                    continue
                
                # 日期过滤
                if start_date or end_date:
                    ts = data.get("timestamp", "")
                    if ts:
                        try:
                            log_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if start_date and log_time < start_date:
                                continue
                            if end_date and log_time > end_date:
                                continue
                        except:
                            pass
                
                # 用户过滤
                if user_id and data.get("user_id") != user_id:
                    continue
                
                # 对话过滤
                if conversation_id and data.get("conversation_id") != conversation_id:
                    continue
                
                timelines.append(data)
                
            except json.JSONDecodeError:
                continue
    
    return timelines


def format_latency(ms: int) -> str:
    """格式化延迟显示"""
    if ms < 1000:
        return f"{ms}ms"
    else:
        return f"{ms/1000:.2f}s"


def get_latency_level(ms: int, thresholds: tuple = (1500, 2500, 4000)) -> str:
    """获取延迟级别标记"""
    if ms < thresholds[0]:
        return "🟢"
    elif ms < thresholds[1]:
        return "🟡"
    elif ms < thresholds[2]:
        return "🟠"
    else:
        return "🔴"


def print_timeline_visualization(timeline: Dict):
    """打印单轮对话的时间轴可视化"""
    
    events = timeline.get("events", {})
    latencies = timeline.get("latencies", {})
    
    if not events:
        return
    
    print(f"\n{'='*70}")
    print(f"  轮次: {timeline.get('round_id', 'N/A')} | "
          f"用户: {timeline.get('user_id', 'N/A')[:8]} | "
          f"对话: {timeline.get('conversation_id', 'N/A')[:12]}")
    print(f"{'='*70}")
    
    # 按时间排序事件
    sorted_events = sorted(
        [(k, v) for k, v in events.items()],
        key=lambda x: x[1].get("timestamp_ms", 0)
    )
    
    if not sorted_events:
        print("  无事件数据")
        return
    
    # 计算基准时间（第一个事件）
    base_time = sorted_events[0][1].get("timestamp_ms", 0)
    
    # 打印时间轴
    print(f"\n  📊 时间轴（相对于用户开始说话）:")
    print(f"  {'-'*60}")
    
    event_labels = {
        "client_speech_start": "👤 用户开始说话",
        "client_speech_end": "👤 用户结束说话",
        "server_audio_first": "📥 服务端收到首帧",
        "server_audio_last": "📥 服务端收到末帧",
        "asr_start": "🎤 ASR 开始",
        "asr_end": "🎤 ASR 结束",
        "llm_start": "🤖 LLM 开始",
        "llm_first_token": "🤖 LLM 首 Token",
        "llm_end": "🤖 LLM 结束",
        "tts_start": "🔊 TTS 开始",
        "tts_first_chunk": "🔊 TTS 首块",
        "tts_end": "🔊 TTS 结束",
        "client_audio_first": "📤 用户端收到首块",
        "client_audio_end": "📤 用户端播放结束",
    }
    
    for event_type, event_data in sorted_events:
        ts = event_data.get("timestamp_ms", 0)
        relative_ms = ts - base_time
        source = event_data.get("source", "?")[0].upper()
        label = event_labels.get(event_type, event_type)
        
        # 计算进度条位置（假设总时长 10 秒）
        max_duration = 10000  # 10秒
        bar_width = 40
        pos = min(int(relative_ms / max_duration * bar_width), bar_width - 1)
        bar = [" "] * bar_width
        bar[pos] = "█"
        bar_str = "".join(bar)
        
        print(f"  {relative_ms:>6}ms |{bar_str}| {label} [{source}]")
    
    # 打印延迟统计
    print(f"\n  ⏱️ 延迟统计:")
    print(f"  {'-'*60}")
    
    latency_labels = {
        "user_perceived_ms": ("👁️ 用户感知延迟", (1500, 2500, 4000)),
        "user_speech_duration_ms": ("🗣️ 用户说话时长", (10000, 20000, 30000)),
        "asr_ms": ("🎤 ASR 耗时", (500, 1000, 2000)),
        "llm_ttft_ms": ("🤖 LLM TTFT", (500, 1000, 2000)),
        "llm_total_ms": ("🤖 LLM 总耗时", (1000, 2000, 4000)),
        "tts_first_chunk_ms": ("🔊 TTS 首块", (300, 500, 1000)),
        "tts_total_ms": ("🔊 TTS 总耗时", (1000, 2000, 4000)),
        "network_upload_ms": ("📥 上行网络", (200, 500, 1000)),
        "network_download_ms": ("📤 下行网络", (200, 500, 1000)),
        "ai_audio_duration_ms": ("🔊 AI 回复时长", (5000, 10000, 20000)),
        "e2e_total_ms": ("🔄 端到端总时长", (5000, 10000, 20000)),
    }
    
    for key, (label, thresholds) in latency_labels.items():
        if key in latencies:
            ms = latencies[key]
            level = get_latency_level(ms, thresholds)
            print(f"  {level} {label}: {format_latency(ms)}")


def print_statistics(timelines: List[Dict]):
    """打印统计信息"""
    
    if not timelines:
        print("  无数据")
        return
    
    # 收集所有延迟数据
    all_latencies = defaultdict(list)
    
    for timeline in timelines:
        latencies = timeline.get("latencies", {})
        for key, value in latencies.items():
            if value and value > 0:
                all_latencies[key].append(value)
    
    print(f"\n{'='*70}")
    print(f"  📈 延迟统计摘要 (共 {len(timelines)} 轮对话)")
    print(f"{'='*70}\n")
    
    latency_labels = {
        "user_perceived_ms": "👁️ 用户感知延迟",
        "asr_ms": "🎤 ASR 耗时",
        "llm_ttft_ms": "🤖 LLM TTFT",
        "llm_total_ms": "🤖 LLM 总耗时",
        "tts_first_chunk_ms": "🔊 TTS 首块",
        "tts_total_ms": "🔊 TTS 总耗时",
        "network_upload_ms": "📥 上行网络",
        "network_download_ms": "📤 下行网络",
    }
    
    print(f"  {'指标':<20} | {'P50':>8} | {'P90':>8} | {'P99':>8} | {'平均':>8} | {'最大':>8} | {'样本':>6}")
    print(f"  {'-'*20}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*6}")
    
    for key, label in latency_labels.items():
        if key in all_latencies and all_latencies[key]:
            values = sorted(all_latencies[key])
            n = len(values)
            
            p50 = values[n // 2]
            p90 = values[int(n * 0.9)]
            p99 = values[int(n * 0.99)] if n >= 100 else values[-1]
            avg = sum(values) // n
            max_val = values[-1]
            
            print(f"  {label:<20} | {format_latency(p50):>8} | {format_latency(p90):>8} | "
                  f"{format_latency(p99):>8} | {format_latency(avg):>8} | {format_latency(max_val):>8} | {n:>6}")
    
    # 用户感知延迟分布
    if "user_perceived_ms" in all_latencies:
        values = all_latencies["user_perceived_ms"]
        excellent = len([v for v in values if v < 1500])
        good = len([v for v in values if 1500 <= v < 2500])
        acceptable = len([v for v in values if 2500 <= v < 4000])
        poor = len([v for v in values if v >= 4000])
        
        print(f"\n  📊 用户感知延迟分布:")
        print(f"  🟢 优秀 (<1.5s):    {excellent:>4} ({excellent/len(values)*100:>5.1f}%)")
        print(f"  🟡 良好 (1.5-2.5s): {good:>4} ({good/len(values)*100:>5.1f}%)")
        print(f"  🟠 可接受 (2.5-4s): {acceptable:>4} ({acceptable/len(values)*100:>5.1f}%)")
        print(f"  🔴 较差 (>4s):      {poor:>4} ({poor/len(values)*100:>5.1f}%)")


def print_user_summary(timelines: List[Dict]):
    """按用户统计"""
    
    user_stats = defaultdict(lambda: {"count": 0, "latencies": []})
    
    for timeline in timelines:
        user_id = timeline.get("user_id", "unknown")[:8]
        user_stats[user_id]["count"] += 1
        
        user_perceived = timeline.get("latencies", {}).get("user_perceived_ms")
        if user_perceived:
            user_stats[user_id]["latencies"].append(user_perceived)
    
    print(f"\n  📊 用户统计:")
    print(f"  {'-'*50}")
    
    for user_id, stats in sorted(user_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        count = stats["count"]
        latencies = stats["latencies"]
        
        if latencies:
            avg = sum(latencies) // len(latencies)
            level = get_latency_level(avg)
            print(f"  👤 {user_id:<10} | 对话数: {count:>3} | 平均延迟: {level} {format_latency(avg)}")
        else:
            print(f"  👤 {user_id:<10} | 对话数: {count:>3} | 平均延迟: N/A")


def main():
    parser = argparse.ArgumentParser(description='时间轴分析工具')
    parser.add_argument('--days', '-d', type=int, default=1, help='分析最近几天的数据')
    parser.add_argument('--user', '-u', type=str, help='指定用户 ID')
    parser.add_argument('--conv', '-c', type=str, help='指定对话 ID')
    parser.add_argument('--detail', action='store_true', help='显示详细时间轴')
    parser.add_argument('--limit', '-l', type=int, default=10, help='详细模式下最多显示几轮')
    args = parser.parse_args()
    
    # 计算日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    print("=" * 70)
    print(f"  ⏱️ 时间轴分析报告")
    print(f"  📅 时间范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    if args.user:
        print(f"  👤 用户: {args.user}")
    if args.conv:
        print(f"  💬 对话: {args.conv}")
    print("=" * 70)
    
    # 加载数据
    timelines = load_timeline_logs(
        start_date=start_date,
        end_date=end_date,
        user_id=args.user,
        conversation_id=args.conv
    )
    
    print(f"\n  📊 找到 {len(timelines)} 轮对话数据")
    
    if not timelines:
        print("\n  ❌ 无数据，请检查日志文件或时间范围")
        return
    
    # 显示详细时间轴
    if args.detail:
        print(f"\n  📋 详细时间轴（最近 {args.limit} 轮）:")
        for timeline in timelines[-args.limit:]:
            print_timeline_visualization(timeline)
    
    # 统计信息
    print_statistics(timelines)
    
    # 用户统计
    if not args.user:
        print_user_summary(timelines)
    
    print(f"\n{'='*70}")
    print(f"  分析完成")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
