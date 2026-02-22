#!/usr/bin/env python3
"""
用户感知延迟分析 - 对话文本 + 延迟变化图

用户感知延迟 = 用户说完话 → AI 开始发出声音
计算方式：从日志中提取 "Total Latency: XXXms (用户停止说话 → AI 开始说话)"
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

# Supabase 配置
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


def get_messages_from_db(conversation_id: str) -> List[Dict]:
    """从数据库获取对话消息"""
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = client.table("messages").select("*").eq(
        "conversation_id", conversation_id
    ).order("round_number").execute()
    return result.data


def extract_latency_from_logs(start_date: datetime, end_date: datetime) -> List[Dict]:
    """
    从日志中提取用户感知延迟
    
    用户感知延迟 = Total Latency (用户停止说话 → AI 开始说话)
    """
    interactions = []
    
    # 读取日志文件
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 缓存：用于关联用户输入和延迟
    pending_input = {}  # trace_id -> {time, user_input, user_id}
    
    for line in lines:
        # 检查日期范围
        date_match = re.match(r'^(\d{4}-\d{2}-\d{2})', line)
        if date_match:
            log_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
            if not (start_date.date() <= log_date.date() <= end_date.date()):
                continue
        
        # 尝试解析 JSON 格式日志
        json_match = re.search(r'\{.*\}', line)
        if json_match:
            try:
                log = json.loads(json_match.group())
                timestamp = log.get("timestamp", "")
                user_id = log.get("user_id", "anonymous")
                trace_id = log.get("trace_id", "")
                message = log.get("message", "")
                
                # 提取用户输入
                input_match = re.search(r'用户输入: (.+?)\.\.\.', message)
                if input_match and trace_id:
                    pending_input[trace_id] = {
                        "time": timestamp,
                        "user_input": input_match.group(1),
                        "user_id": user_id,
                        "trace_id": trace_id
                    }
                
                # 提取 Total Latency (用户感知延迟)
                latency_match = re.search(r'Total Latency:\s*(\d+)ms', message)
                if latency_match:
                    latency_ms = int(latency_match.group(1))
                    
                    # 尝试找到对应的用户输入
                    interaction = {
                        "timestamp": timestamp,
                        "user_id": user_id if user_id != "anonymous" else None,
                        "trace_id": trace_id,
                        "latency_ms": latency_ms,
                        "user_input": None
                    }
                    
                    # 匹配用户输入（基于 trace_id 或时间接近）
                    if trace_id and trace_id in pending_input:
                        interaction["user_input"] = pending_input[trace_id]["user_input"]
                        if not interaction["user_id"]:
                            interaction["user_id"] = pending_input[trace_id]["user_id"]
                    
                    interactions.append(interaction)
                
            except json.JSONDecodeError:
                pass
        else:
            # 非 JSON 格式日志
            # 提取时间和用户输入
            time_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if time_match:
                timestamp = time_match.group(1)
                
                input_match = re.search(r'用户输入: (.+?)\.\.\.', line)
                if input_match:
                    # 使用时间戳作为临时 key
                    pending_input[timestamp[:16]] = {  # 精确到分钟
                        "time": timestamp,
                        "user_input": input_match.group(1),
                        "user_id": None,
                        "trace_id": ""
                    }
    
    return interactions


def generate_report(days: int = 2):
    """生成完整报告"""
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print("=" * 80)
    print(f"  📊 用户感知延迟分析报告")
    print(f"  📅 时间范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    print("=" * 80)
    
    # 1. 从数据库获取用户信息
    print("\n🔍 正在查询数据库...")
    user_map = get_users_from_db()
    conversations = get_conversations_from_db(start_date, end_date)
    
    print(f"   找到 {len(conversations)} 条对话")
    
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
    print(f"  1. 活跃用户统计 (共 {len(active_users)} 人)")
    print(f"{'='*80}\n")
    
    for username, info in sorted(active_users.items(), key=lambda x: x[1]["count"], reverse=True):
        print(f"   👤 {username:<20} | 对话数: {info['count']}")
    
    # 2. 从日志提取延迟数据
    print(f"\n{'='*80}")
    print(f"  2. 用户感知延迟提取")
    print(f"{'='*80}\n")
    
    print("   📖 用户感知延迟 = 用户说完话 → AI 开始发出声音")
    print("   📖 计算方式: 日志中的 'Total Latency: XXXms'\n")
    
    interactions = extract_latency_from_logs(start_date, end_date)
    print(f"   找到 {len(interactions)} 条延迟记录\n")
    
    # 3. 按用户分组统计
    user_interactions = defaultdict(list)
    for inter in interactions:
        uid = inter.get("user_id") or "unknown"
        username = user_map.get(uid, uid[:8] if len(uid) > 8 else uid)
        user_interactions[username].append(inter)
    
    print(f"{'='*80}")
    print(f"  3. 对话文本 + 延迟变化")
    print(f"{'='*80}")
    
    # 输出每个用户的交互记录
    for username, inters in sorted(user_interactions.items(), key=lambda x: len(x[1]), reverse=True):
        if username in ["unknown", "anonymous"]:
            continue
            
        print(f"\n   👤 用户: {username}")
        print(f"   交互次数: {len(inters)}")
        
        latencies = [i["latency_ms"] for i in inters]
        if latencies:
            avg_lat = sum(latencies) / len(latencies)
            print(f"   平均延迟: {avg_lat:.0f}ms ({avg_lat/1000:.2f}s)")
            print(f"   最小/最大: {min(latencies)}ms / {max(latencies)}ms")
        
        print(f"\n   {'序号':<4} | {'延迟':>8} | 用户说")
        print(f"   {'-'*4}-+-{'-'*8}-+-{'-'*40}")
        
        for i, inter in enumerate(inters[:20], 1):  # 最多显示20条
            lat = inter["latency_ms"]
            user_input = inter.get("user_input", "(未记录)")[:35]
            
            # 延迟分级标记
            if lat < 1500:
                level = "🟢"
            elif lat < 2500:
                level = "🟡"
            elif lat < 4000:
                level = "🟠"
            else:
                level = "🔴"
            
            print(f"   {i:<4} | {level} {lat:>5}ms | {user_input}...")
        
        if len(inters) > 20:
            print(f"   ... 还有 {len(inters) - 20} 条记录")
        
        # 延迟变化趋势（ASCII 图）
        if len(latencies) >= 3:
            print(f"\n   📈 延迟变化趋势:")
            max_lat = max(latencies)
            min_lat = min(latencies)
            range_lat = max_lat - min_lat or 1
            
            # 归一化到 0-20 的高度
            heights = [int((lat - min_lat) / range_lat * 15) for lat in latencies[:30]]
            
            # 绘制 ASCII 图
            for h in range(15, -1, -1):
                line = "      "
                for height in heights:
                    if height >= h:
                        line += "█"
                    else:
                        line += " "
                if h == 15:
                    line += f" {max_lat}ms"
                elif h == 0:
                    line += f" {min_lat}ms"
                print(line)
            print(f"      {''.join([str(i%10) for i in range(1, len(heights)+1)])}")
    
    # 4. 总体统计
    all_latencies = [i["latency_ms"] for i in interactions]
    if all_latencies:
        print(f"\n{'='*80}")
        print(f"  4. 总体延迟统计")
        print(f"{'='*80}\n")
        
        all_latencies.sort()
        n = len(all_latencies)
        
        print(f"   总交互数: {n}")
        print(f"   平均延迟: {sum(all_latencies)/n:.0f}ms ({sum(all_latencies)/n/1000:.2f}s)")
        print(f"   P50: {all_latencies[n//2]:.0f}ms")
        print(f"   P90: {all_latencies[int(n*0.9)]:.0f}ms")
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
