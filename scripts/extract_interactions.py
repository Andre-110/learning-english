#!/usr/bin/env python3
"""
提取交互文本和延迟的对应关系
"""

import os
import sys
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")


def extract_interactions(log_file: str, target_date: datetime) -> List[Dict]:
    """提取交互数据"""
    
    interactions = []
    current_interaction = {}
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            # 检查日期
            date_match = re.match(r'^(\d{4}-\d{2}-\d{2})', line)
            if date_match:
                log_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                if log_date.date() != target_date.date():
                    continue
            else:
                continue
            
            # 提取时间
            time_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if time_match:
                current_time = time_match.group(1)
            
            # 用户输入
            user_input_match = re.search(r'用户输入: (.+?)\.\.\.', line)
            if user_input_match:
                if current_interaction:
                    interactions.append(current_interaction)
                current_interaction = {
                    "time": current_time,
                    "user_input": user_input_match.group(1)
                }
            
            # transcription
            trans_match = re.search(r'transcription=([^\.]+)', line)
            if trans_match and "user_input" not in current_interaction:
                if current_interaction:
                    interactions.append(current_interaction)
                current_interaction = {
                    "time": current_time,
                    "user_input": trans_match.group(1)
                }
            
            # AI 回复
            reply_match = re.search(r'回复: (.+?)\.\.\.', line)
            if reply_match and current_interaction:
                current_interaction["ai_reply"] = reply_match.group(1)
            
            # Total Latency
            latency_match = re.search(r'Total Latency: (\d+)ms', line)
            if latency_match and current_interaction:
                current_interaction["total_latency_ms"] = int(latency_match.group(1))
            
            # LLM 耗时
            llm_match = re.search(r'总耗时: ([\d.]+)s', line)
            if llm_match and current_interaction:
                current_interaction["llm_total_s"] = float(llm_match.group(1))
    
    if current_interaction:
        interactions.append(current_interaction)
    
    return interactions


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', '-d', help='目标日期 YYYY-MM-DD')
    args = parser.parse_args()
    
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime.now() - timedelta(days=1)
    
    log_file = os.path.join(LOG_DIR, "app.log")
    
    print("=" * 80)
    print(f"  📝 交互文本与延迟对照表 - {target_date.strftime('%Y-%m-%d')}")
    print("=" * 80)
    
    interactions = extract_interactions(log_file, target_date)
    
    # 过滤有效交互
    valid = [i for i in interactions if i.get("user_input") and i.get("total_latency_ms")]
    
    print(f"\n✅ 共提取 {len(valid)} 条有效交互\n")
    
    # 按延迟排序
    sorted_by_latency = sorted(valid, key=lambda x: x.get("total_latency_ms", 0), reverse=True)
    
    print("-" * 80)
    print(f"{'时间':<20} | {'延迟':>8} | 用户说 → AI 回复")
    print("-" * 80)
    
    for i, item in enumerate(sorted_by_latency[:30]):  # 显示前30条
        time = item.get("time", "N/A")[-8:]  # 只取时间部分
        latency = item.get("total_latency_ms", 0)
        user = item.get("user_input", "")[:25]
        ai = item.get("ai_reply", "")[:35]
        
        # 延迟分级颜色标记
        if latency < 1500:
            level = "🟢"
        elif latency < 2500:
            level = "🟡"
        elif latency < 4000:
            level = "🟠"
        else:
            level = "🔴"
        
        print(f"{time:<20} | {level} {latency:>5}ms | 👤 {user}...")
        if ai:
            print(f"{'':>34} | 🤖 {ai}...")
        print()
    
    # 统计
    print("=" * 80)
    print("  📊 延迟统计")
    print("=" * 80)
    
    latencies = [i["total_latency_ms"] for i in valid]
    if latencies:
        latencies.sort()
        n = len(latencies)
        
        print(f"\n   总交互数: {n}")
        print(f"   平均延迟: {sum(latencies)/n:.0f}ms")
        print(f"   P50延迟:  {latencies[n//2]:.0f}ms")
        print(f"   P90延迟:  {latencies[int(n*0.9)]:.0f}ms")
        print(f"   最小延迟: {min(latencies):.0f}ms")
        print(f"   最大延迟: {max(latencies):.0f}ms")
        
        # 体验分级
        excellent = len([x for x in latencies if x < 1500])
        good = len([x for x in latencies if 1500 <= x < 2500])
        acceptable = len([x for x in latencies if 2500 <= x < 4000])
        poor = len([x for x in latencies if x >= 4000])
        
        print(f"\n   🟢 优秀 (<1.5s):    {excellent:>3} ({excellent/n*100:>5.1f}%)")
        print(f"   🟡 良好 (1.5-2.5s): {good:>3} ({good/n*100:>5.1f}%)")
        print(f"   🟠 可接受 (2.5-4s): {acceptable:>3} ({acceptable/n*100:>5.1f}%)")
        print(f"   🔴 较差 (>4s):      {poor:>3} ({poor/n*100:>5.1f}%)")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
