#!/usr/bin/env python3
"""
从日志文件中提取延迟指标

功能:
1. 解析 app.log 中的延迟数据
2. 按用户/对话统计
3. 生成延迟分析报告
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")


def parse_log_line(line: str) -> Dict[str, Any]:
    """解析 JSON 格式的日志行"""
    try:
        return json.loads(line.strip())
    except:
        return None


def extract_latency_from_message(message: str) -> Dict[str, float]:
    """从日志消息中提取延迟数据"""
    latencies = {}
    
    # 模式1: [性能-双阈值] 发送给前端的 latency: {...}
    if "latency:" in message:
        match = re.search(r"latency:\s*(\{[^}]+\})", message)
        if match:
            try:
                data = eval(match.group(1))  # 安全的字典解析
                if isinstance(data, dict):
                    latencies.update(data)
            except:
                pass
    
    # 模式2: Total Latency: 2262ms
    match = re.search(r"Total Latency:\s*(\d+)ms", message)
    if match:
        latencies["total_latency_ms"] = int(match.group(1))
    
    # 模式3: LLM TTFT: 1174ms
    match = re.search(r"LLM TTFT\s*:\s*(\d+)ms", message)
    if match:
        latencies["llm_ttft_ms"] = int(match.group(1))
    
    # 模式4: [LLM] 首字延迟 (TTFT): 1.17s
    match = re.search(r"首字延迟.*?:\s*([\d.]+)s", message)
    if match:
        latencies["llm_ttft_s"] = float(match.group(1))
    
    # 模式5: [TTS Stream] 首块延迟: 1000ms
    match = re.search(r"\[TTS.*?\].*?首块延迟:\s*(\d+)ms", message)
    if match:
        latencies["tts_first_chunk_ms"] = int(match.group(1))
    
    # 模式6: [MiniMax TTS Stream] 首块延迟: 596ms
    match = re.search(r"MiniMax.*首块延迟:\s*(\d+)ms", message)
    if match:
        latencies["minimax_tts_first_ms"] = int(match.group(1))
    
    # 模式7: [LLM] ⏱️ 延迟分析: history_len=12, tokens≈2208, latency=5218ms
    match = re.search(r"延迟分析:.*?latency=(\d+)ms", message)
    if match:
        latencies["llm_total_ms"] = int(match.group(1))
    
    # 模式8: ASR 延迟
    match = re.search(r"ASR[^\d]*?(\d+)ms", message)
    if match:
        latencies["asr_ms"] = int(match.group(1))
    
    return latencies


def analyze_log_file(log_file: str, target_date: datetime = None) -> Dict[str, Any]:
    """分析日志文件，提取延迟数据"""
    
    if not os.path.exists(log_file):
        print(f"❌ 日志文件不存在: {log_file}")
        return {}
    
    # 统计数据
    user_latencies = defaultdict(list)  # user_id -> [latency records]
    conversation_latencies = defaultdict(list)  # conversation_id -> [latency records]
    all_latencies = defaultdict(list)  # metric_name -> [values]
    
    total_lines = 0
    matched_lines = 0
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            total_lines += 1
            log = parse_log_line(line)
            if not log:
                continue
            
            # 解析时间戳
            timestamp_str = log.get("timestamp", "")
            try:
                if timestamp_str.endswith("Z"):
                    timestamp_str = timestamp_str[:-1]
                log_time = datetime.fromisoformat(timestamp_str)
                
                # 过滤日期
                if target_date:
                    if log_time.date() != target_date.date():
                        continue
            except:
                continue
            
            # 提取延迟数据
            message = log.get("message", "")
            latencies = extract_latency_from_message(message)
            
            if latencies:
                matched_lines += 1
                user_id = log.get("user_id", "anonymous")
                trace_id = log.get("trace_id", "")
                
                record = {
                    "timestamp": timestamp_str,
                    "user_id": user_id,
                    "trace_id": trace_id,
                    **latencies
                }
                
                # 记录到各个维度
                user_latencies[user_id].append(record)
                if trace_id:
                    conversation_latencies[trace_id].append(record)
                
                # 汇总各指标
                for key, value in latencies.items():
                    if isinstance(value, (int, float)):
                        all_latencies[key].append(value)
    
    return {
        "total_lines": total_lines,
        "matched_lines": matched_lines,
        "user_latencies": dict(user_latencies),
        "conversation_latencies": dict(conversation_latencies),
        "all_latencies": dict(all_latencies)
    }


def calc_stats(values: List[float]) -> Dict[str, float]:
    """计算统计数据"""
    if not values:
        return {"count": 0, "avg": 0, "min": 0, "max": 0, "p50": 0, "p90": 0, "p99": 0}
    
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    def percentile(p):
        idx = int(n * p / 100)
        return sorted_values[min(idx, n - 1)]
    
    return {
        "count": n,
        "avg": round(sum(values) / n, 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "p50": round(percentile(50), 2),
        "p90": round(percentile(90), 2),
        "p99": round(percentile(99), 2)
    }


def print_section(title: str, char: str = "="):
    """打印分节标题"""
    print(f"\n{char * 70}")
    print(f"  {title}")
    print(f"{char * 70}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='从日志中提取延迟指标')
    parser.add_argument('--date', '-d', help='目标日期 (YYYY-MM-DD)，默认为昨天')
    parser.add_argument('--log', '-l', default='app.log', help='日志文件名')
    args = parser.parse_args()
    
    # 确定目标日期
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime.now() - timedelta(days=1)
    
    log_file = os.path.join(LOG_DIR, args.log)
    
    print("=" * 70)
    print("  📊 LinguaCoach 延迟指标分析报告")
    print("=" * 70)
    print(f"\n📅 分析日期: {target_date.strftime('%Y-%m-%d')}")
    print(f"📁 日志文件: {log_file}")
    
    # 分析日志
    result = analyze_log_file(log_file, target_date)
    
    if not result:
        print("\n❌ 未能解析日志文件")
        return
    
    print(f"\n📝 扫描行数: {result['total_lines']:,}")
    print(f"✅ 匹配延迟记录: {result['matched_lines']:,}")
    
    # 1. 整体延迟统计
    print_section("1. 整体延迟统计 (ms)")
    all_latencies = result.get("all_latencies", {})
    
    if not all_latencies:
        print("   ⚠️ 未找到延迟数据")
    else:
        # 显示各指标的统计
        priority_metrics = [
            ("total_latency_ms", "Total Latency (User→AI)"),
            ("total_ms", "Total (alt format)"),
            ("llm_ttft_ms", "LLM TTFT"),
            ("llm_ttft_s", "LLM TTFT (sec)"),
            ("llm_total_ms", "LLM Total"),
            ("llm_ms", "LLM Duration"),
            ("tts_first_chunk_ms", "TTS First Chunk"),
            ("minimax_tts_first_ms", "MiniMax TTS First"),
            ("tts_ms", "TTS Total"),
            ("asr_ms", "ASR Duration"),
            ("stt", "STT Duration"),
        ]
        
        print(f"\n   {'Metric':<28} | {'Count':>6} | {'Avg':>8} | {'P50':>8} | {'P90':>8} | {'P99':>8} | {'Max':>8}")
        print(f"   {'-'*28}-+-{'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}")
        
        for key, label in priority_metrics:
            values = all_latencies.get(key, [])
            if values:
                stats = calc_stats(values)
                # 如果是秒，转换为毫秒显示
                multiplier = 1000 if key.endswith("_s") else 1
                print(f"   {label:<28} | {stats['count']:>6} | {stats['avg']*multiplier:>8.0f} | {stats['p50']*multiplier:>8.0f} | {stats['p90']*multiplier:>8.0f} | {stats['p99']*multiplier:>8.0f} | {stats['max']*multiplier:>8.0f}")
        
        # 显示其他指标
        shown_keys = set(k for k, _ in priority_metrics)
        other_keys = set(all_latencies.keys()) - shown_keys
        for key in other_keys:
            values = all_latencies[key]
            if values and isinstance(values[0], (int, float)):
                stats = calc_stats(values)
                print(f"   {key:<28} | {stats['count']:>6} | {stats['avg']:>8.0f} | {stats['p50']:>8.0f} | {stats['p90']:>8.0f} | {stats['p99']:>8.0f} | {stats['max']:>8.0f}")
    
    # 2. 按用户统计
    print_section("2. 按用户延迟统计")
    user_latencies = result.get("user_latencies", {})
    
    if not user_latencies:
        print("   ⚠️ 未找到用户数据")
    else:
        print(f"\n   共有 {len(user_latencies)} 个用户有延迟记录\n")
        
        for user_id, records in sorted(user_latencies.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            # 提取该用户的总延迟
            total_latencies = []
            llm_ttft_list = []
            tts_first_list = []
            
            for r in records:
                if "total_latency_ms" in r:
                    total_latencies.append(r["total_latency_ms"])
                if "total_ms" in r:
                    total_latencies.append(r["total_ms"])
                if "llm_ttft_ms" in r:
                    llm_ttft_list.append(r["llm_ttft_ms"])
                if "llm_ttft_s" in r:
                    llm_ttft_list.append(r["llm_ttft_s"] * 1000)
                if "tts_first_chunk_ms" in r:
                    tts_first_list.append(r["tts_first_chunk_ms"])
                if "minimax_tts_first_ms" in r:
                    tts_first_list.append(r["minimax_tts_first_ms"])
            
            user_short = user_id[:20] + "..." if len(user_id) > 20 else user_id
            print(f"   👤 {user_short}")
            print(f"      记录数: {len(records)}")
            
            if total_latencies:
                stats = calc_stats(total_latencies)
                print(f"      总延迟: avg={stats['avg']:.0f}ms, p50={stats['p50']:.0f}ms, p90={stats['p90']:.0f}ms, max={stats['max']:.0f}ms")
            if llm_ttft_list:
                stats = calc_stats(llm_ttft_list)
                print(f"      LLM TTFT: avg={stats['avg']:.0f}ms, p50={stats['p50']:.0f}ms, max={stats['max']:.0f}ms")
            if tts_first_list:
                stats = calc_stats(tts_first_list)
                print(f"      TTS First: avg={stats['avg']:.0f}ms, p50={stats['p50']:.0f}ms, max={stats['max']:.0f}ms")
            print()
    
    # 3. 按对话统计 (取前5个)
    print_section("3. 按对话延迟统计 (Top 10)")
    conversation_latencies = result.get("conversation_latencies", {})
    
    if not conversation_latencies:
        print("   ⚠️ 未找到对话数据")
    else:
        # 按记录数排序
        sorted_convs = sorted(conversation_latencies.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        
        for conv_id, records in sorted_convs:
            if not conv_id:
                continue
            
            total_latencies = []
            for r in records:
                if "total_latency_ms" in r:
                    total_latencies.append(r["total_latency_ms"])
                if "total_ms" in r:
                    total_latencies.append(r["total_ms"])
            
            conv_short = conv_id[:25]
            print(f"\n   🗣️ {conv_short}")
            print(f"      用户: {records[0].get('user_id', 'N/A')[:20]}...")
            print(f"      延迟记录: {len(records)}")
            
            if total_latencies:
                stats = calc_stats(total_latencies)
                print(f"      总延迟: avg={stats['avg']:.0f}ms, min={stats['min']:.0f}ms, max={stats['max']:.0f}ms")
    
    # 4. 用户体验分析
    print_section("4. 用户体验分析 (延迟分级)")
    
    # 收集所有总延迟
    all_total = all_latencies.get("total_latency_ms", []) + all_latencies.get("total_ms", [])
    
    if all_total:
        excellent = len([x for x in all_total if x < 1500])  # < 1.5s
        good = len([x for x in all_total if 1500 <= x < 2500])  # 1.5-2.5s
        acceptable = len([x for x in all_total if 2500 <= x < 4000])  # 2.5-4s
        poor = len([x for x in all_total if x >= 4000])  # >= 4s
        
        total = len(all_total)
        
        print(f"\n   📊 总延迟分布 (用户停止说话 → AI 开始说话)")
        print(f"\n   🟢 优秀 (<1.5s):  {excellent:>5} 次 ({excellent/total*100:>5.1f}%)")
        print(f"   🟡 良好 (1.5-2.5s): {good:>5} 次 ({good/total*100:>5.1f}%)")
        print(f"   🟠 可接受 (2.5-4s): {acceptable:>5} 次 ({acceptable/total*100:>5.1f}%)")
        print(f"   🔴 较差 (>4s):   {poor:>5} 次 ({poor/total*100:>5.1f}%)")
        print(f"\n   总计: {total} 次交互")
        
        # 计算整体体验评分
        score = (excellent * 100 + good * 75 + acceptable * 50 + poor * 25) / total if total > 0 else 0
        print(f"\n   🏆 整体体验评分: {score:.1f}/100")
    else:
        print("   ⚠️ 未找到总延迟数据")
    
    print("\n" + "=" * 70)
    print("  报告生成完成")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
