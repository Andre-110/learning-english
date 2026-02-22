#!/usr/bin/env python3
"""
用户感知延迟分析 V2 - 通过时间顺序配对

用户感知延迟 = 用户说完话 → AI 开始发出声音
从日志中提取 "Total Latency: XXXms (用户停止说话 → AI 开始说话)"
"""

import os
import sys
import re
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://uxnqqkuviqlptltcepat.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV4bnFxa3V2aXFscHRsdGNlcGF0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwODIzMDgsImV4cCI6MjA4MDY1ODMwOH0.oI7uVTWBXDnEhRgAsy_L4SZf2vGDpacwfKoEDS1DHsc"

LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "app.log")


def get_users_from_db() -> Dict[str, str]:
    """从数据库获取 user_id -> username 映射"""
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = client.table("users").select("user_id, username").execute()
    return {u["user_id"]: u["username"] for u in result.data}


def get_conversations_from_db(start_date: datetime, end_date: datetime) -> List[Dict]:
    """从数据库获取指定日期范围的对话"""
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = client.table("conversations").select("*").gte(
        "started_at", start_date.isoformat()
    ).lte(
        "started_at", end_date.isoformat()
    ).order("started_at", desc=True).execute()
    return result.data


def extract_interactions(start_date: datetime, end_date: datetime) -> List[Dict]:
    """
    从日志中按时间顺序提取交互，配对用户输入和延迟
    """
    
    # 第一遍：提取所有用户输入
    user_inputs = []
    # 第二遍：提取所有延迟
    latencies = []
    
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            # 检查日期
            date_match = re.match(r'^(\d{4}-\d{2}-\d{2})', line)
            if not date_match:
                continue
            
            log_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
            if not (start_date.date() <= log_date.date() <= end_date.date()):
                continue
            
            # 提取时间戳
            time_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if not time_match:
                continue
            timestamp = time_match.group(1)
            
            # 提取用户输入
            input_match = re.search(r'用户输入: (.+?)\.\.\.', line)
            if input_match:
                user_inputs.append({
                    "timestamp": timestamp,
                    "user_input": input_match.group(1)
                })
            
            # 提取延迟
            latency_match = re.search(r'Total Latency:\s*(\d+)ms', line)
            if latency_match:
                latencies.append({
                    "timestamp": timestamp,
                    "latency_ms": int(latency_match.group(1))
                })
    
    # 配对：每个延迟匹配之前最近的用户输入
    interactions = []
    input_idx = 0
    
    for lat in latencies:
        lat_time = datetime.strptime(lat["timestamp"], "%Y-%m-%d %H:%M:%S")
        
        # 找到最近的用户输入（在延迟之前的）
        best_input = None
        for i in range(input_idx, len(user_inputs)):
            inp_time = datetime.strptime(user_inputs[i]["timestamp"], "%Y-%m-%d %H:%M:%S")
            if inp_time <= lat_time:
                best_input = user_inputs[i]
                input_idx = i + 1
            else:
                break
        
        interactions.append({
            "timestamp": lat["timestamp"],
            "user_input": best_input["user_input"] if best_input else "(未记录)",
            "latency_ms": lat["latency_ms"]
        })
    
    return interactions


def generate_report(days: int = 2):
    """生成完整报告"""
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print("=" * 80)
    print(f"  📊 用户感知延迟分析报告 (V2)")
    print(f"  📅 时间范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    print("=" * 80)
    
    # 1. 从数据库获取用户和对话统计
    print("\n🔍 正在查询数据库...")
    user_map = get_users_from_db()
    conversations = get_conversations_from_db(start_date, end_date)
    
    # 统计活跃用户
    active_users = {}
    for conv in conversations:
        uid = conv.get("user_id", "")
        if uid:
            username = user_map.get(uid, uid[:8])
            if username not in active_users:
                active_users[username] = {"count": 0, "user_id": uid}
            active_users[username]["count"] += 1
    
    print(f"\n{'='*80}")
    print(f"  1. 活跃用户统计 (共 {len(active_users)} 人，{len(conversations)} 条对话)")
    print(f"{'='*80}\n")
    
    for username, info in sorted(active_users.items(), key=lambda x: x[1]["count"], reverse=True):
        print(f"   👤 {username:<20} | 对话数: {info['count']}")
    
    # 2. 从日志提取交互数据
    print(f"\n{'='*80}")
    print(f"  2. 用户感知延迟 (按时间顺序)")
    print(f"{'='*80}\n")
    
    print("   📖 用户感知延迟 = 用户说完话 → AI 开始发出声音")
    
    interactions = extract_interactions(start_date, end_date)
    print(f"   找到 {len(interactions)} 条交互记录\n")
    
    # 3. 对话文本 + 延迟表格
    print(f"   {'序号':<4} | {'时间':<19} | {'延迟':>8} | 用户说")
    print(f"   {'-'*4}-+-{'-'*19}-+-{'-'*8}-+-{'-'*40}")
    
    for i, inter in enumerate(interactions, 1):
        lat = inter["latency_ms"]
        user_input = inter.get("user_input", "(未记录)")[:38]
        
        # 延迟分级标记
        if lat < 1500:
            level = "🟢"
        elif lat < 2500:
            level = "🟡"
        elif lat < 4000:
            level = "🟠"
        else:
            level = "🔴"
        
        print(f"   {i:<4} | {inter['timestamp']:<19} | {level} {lat:>5}ms | {user_input}")
    
    # 4. 延迟变化图 (ASCII)
    if len(interactions) >= 3:
        print(f"\n{'='*80}")
        print(f"  3. 延迟变化趋势图")
        print(f"{'='*80}\n")
        
        latencies = [i["latency_ms"] for i in interactions]
        max_lat = max(latencies)
        min_lat = min(latencies)
        range_lat = max_lat - min_lat or 1
        
        # 归一化到 0-20 的高度
        heights = [int((lat - min_lat) / range_lat * 18) for lat in latencies]
        
        # 绘制 ASCII 图
        print(f"   延迟(ms)")
        for h in range(18, -1, -1):
            if h == 18:
                label = f"{max_lat:>5}"
            elif h == 9:
                label = f"{(max_lat + min_lat) // 2:>5}"
            elif h == 0:
                label = f"{min_lat:>5}"
            else:
                label = "     "
            
            line = f"   {label} |"
            for height in heights[:50]:  # 最多显示50个点
                if height >= h:
                    line += "█"
                else:
                    line += " "
            print(line)
        
        print(f"         +{'─' * min(len(heights), 50)}")
        print(f"          交互序号 (1 ~ {len(interactions)})")
        
        # 标注特殊点
        print(f"\n   📍 关键点:")
        print(f"      最快: 第{latencies.index(min_lat)+1}次, {min_lat}ms")
        print(f"      最慢: 第{latencies.index(max_lat)+1}次, {max_lat}ms")
    
    # 5. 总体统计
    all_latencies = [i["latency_ms"] for i in interactions]
    if all_latencies:
        print(f"\n{'='*80}")
        print(f"  4. 总体延迟统计")
        print(f"{'='*80}\n")
        
        all_latencies_sorted = sorted(all_latencies)
        n = len(all_latencies_sorted)
        
        print(f"   总交互数: {n}")
        print(f"   平均延迟: {sum(all_latencies)/n:.0f}ms ({sum(all_latencies)/n/1000:.2f}秒)")
        print(f"   P50: {all_latencies_sorted[n//2]:.0f}ms")
        print(f"   P90: {all_latencies_sorted[int(n*0.9)]:.0f}ms")
        print(f"   最小: {min(all_latencies)}ms")
        print(f"   最大: {max(all_latencies)}ms")
        
        # 体验分级
        excellent = len([x for x in all_latencies if x < 1500])
        good = len([x for x in all_latencies if 1500 <= x < 2500])
        acceptable = len([x for x in all_latencies if 2500 <= x < 4000])
        poor = len([x for x in all_latencies if x >= 4000])
        
        print(f"\n   体验分级:")
        print(f"   🟢 优秀 (<1.5s):    {excellent:>4} ({excellent/n*100:>5.1f}%)")
        print(f"   🟡 良好 (1.5-2.5s): {good:>4} ({good/n*100:>5.1f}%)")
        print(f"   🟠 可接受 (2.5-4s): {acceptable:>4} ({acceptable/n*100:>5.1f}%)")
        print(f"   🔴 较差 (>4s):      {poor:>4} ({poor/n*100:>5.1f}%)")
        
        # 体验评分
        score = (excellent * 100 + good * 75 + acceptable * 50 + poor * 25) / n
        print(f"\n   🏆 整体体验评分: {score:.1f}/100")
    
    print(f"\n{'='*80}")
    print(f"  报告完成")
    print(f"{'='*80}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='用户感知延迟分析')
    parser.add_argument('--days', '-d', type=int, default=2, help='分析最近几天的数据 (默认2天)')
    args = parser.parse_args()
    
    generate_report(args.days)


if __name__ == "__main__":
    main()
