#!/usr/bin/env python3
"""
查询昨天的用户测试数据

功能:
1. 查看昨天有哪些用户在测试
2. 查看测试的交互文本
3. 查看用户感知的时间延迟指标
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, Client

# Supabase 配置
SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://uxnqqkuviqlptltcepat.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV4bnFxa3V2aXFscHRsdGNlcGF0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwODIzMDgsImV4cCI6MjA4MDY1ODMwOH0.oI7uVTWBXDnEhRgAsy_L4SZf2vGDpacwfKoEDS1DHsc"


def get_supabase_client() -> Client:
    """获取 Supabase 客户端"""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_yesterday_range():
    """获取昨天的时间范围"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today - timedelta(days=1)
    yesterday_end = today - timedelta(seconds=1)
    return yesterday_start, yesterday_end


def query_users(client: Client) -> List[Dict]:
    """查询所有用户"""
    try:
        result = client.table("users").select("*").execute()
        return result.data
    except Exception as e:
        print(f"❌ 查询用户失败: {e}")
        return []


def query_conversations(client: Client, start_time: datetime = None, end_time: datetime = None) -> List[Dict]:
    """查询对话"""
    try:
        query = client.table("conversations").select("*")
        
        if start_time:
            query = query.gte("started_at", start_time.isoformat())
        if end_time:
            query = query.lte("started_at", end_time.isoformat())
        
        result = query.order("started_at", desc=True).execute()
        return result.data
    except Exception as e:
        print(f"❌ 查询对话失败: {e}")
        return []


def query_messages(client: Client, conversation_id: str) -> List[Dict]:
    """查询消息"""
    try:
        result = client.table("messages").select("*").eq("conversation_id", conversation_id).order("round_number").execute()
        return result.data
    except Exception as e:
        print(f"❌ 查询消息失败: {e}")
        return []


def format_message(msg: Dict) -> str:
    """格式化消息"""
    role = msg.get("sender_role", "unknown")
    content = msg.get("content", "")[:100]  # 截取前100字符
    if len(msg.get("content", "")) > 100:
        content += "..."
    
    emoji = "🤖" if role == "assistant" else "👤"
    return f"  {emoji} [{role}]: {content}"


def print_section(title: str, char: str = "="):
    """打印分节标题"""
    print(f"\n{char * 60}")
    print(f"  {title}")
    print(f"{char * 60}")


def main():
    print("=" * 60)
    print("  LinguaCoach 数据库查询 - 昨天用户测试数据")
    print("=" * 60)
    
    client = get_supabase_client()
    yesterday_start, yesterday_end = get_yesterday_range()
    
    print(f"\n📅 查询时间范围: {yesterday_start.strftime('%Y-%m-%d')} (整天)")
    print(f"   {yesterday_start.isoformat()} ~ {yesterday_end.isoformat()}")
    
    # 1. 查询所有用户
    print_section("1. 用户列表")
    users = query_users(client)
    print(f"   总用户数: {len(users)}")
    
    for user in users:
        user_id = user.get("user_id", "N/A")
        username = user.get("username", "N/A")
        cefr = user.get("cefr_level", "N/A")
        score = user.get("overall_score", 0)
        conv_count = user.get("conversation_count", 0)
        last_login = user.get("last_login_at", "N/A")
        
        print(f"\n   👤 {username}")
        print(f"      ID: {user_id[:16]}...")
        print(f"      等级: {cefr} | 分数: {score} | 对话数: {conv_count}")
        print(f"      最后登录: {last_login}")
    
    # 2. 查询昨天的对话
    print_section("2. 昨天的对话")
    
    # 先查询所有对话，然后在客户端过滤
    all_conversations = query_conversations(client)
    
    # 过滤昨天的对话
    yesterday_conversations = []
    for conv in all_conversations:
        started_at = conv.get("started_at")
        if started_at:
            try:
                if started_at.endswith("Z"):
                    started_at = started_at[:-1] + "+00:00"
                conv_time = datetime.fromisoformat(started_at.replace("+00:00", ""))
                if yesterday_start.date() == conv_time.date():
                    yesterday_conversations.append(conv)
            except Exception as e:
                pass
    
    if not yesterday_conversations:
        print(f"   ⚠️ 昨天 ({yesterday_start.strftime('%Y-%m-%d')}) 没有对话记录")
        
        # 查看最近的对话
        print("\n   📊 最近 5 条对话记录:")
        recent_convs = all_conversations[:5]
        for conv in recent_convs:
            conv_id = conv.get("conversation_id", "N/A")
            user_id = conv.get("user_id", "N/A")
            started_at = conv.get("started_at", "N/A")
            state = conv.get("state", "N/A")
            
            print(f"\n   🗣️ 对话: {conv_id[:20]}...")
            print(f"      用户: {user_id[:16]}...")
            print(f"      开始: {started_at}")
            print(f"      状态: {state}")
    else:
        print(f"   ✅ 昨天共有 {len(yesterday_conversations)} 条对话\n")
        
        for conv in yesterday_conversations:
            conv_id = conv.get("conversation_id", "N/A")
            user_id = conv.get("user_id", "N/A")
            started_at = conv.get("started_at", "N/A")
            state = conv.get("state", "N/A")
            
            print(f"   🗣️ 对话: {conv_id}")
            print(f"      用户: {user_id}")
            print(f"      开始: {started_at}")
            print(f"      状态: {state}")
            
            # 查询该对话的消息
            messages = query_messages(client, conv_id)
            print(f"      消息数: {len(messages)}")
            
            # 显示前 5 条消息
            if messages:
                print("      消息摘要:")
                for msg in messages[:5]:
                    print(format_message(msg))
                if len(messages) > 5:
                    print(f"      ... 还有 {len(messages) - 5} 条消息")
            print()
    
    # 3. 延迟指标
    print_section("3. 延迟指标")
    print("   📊 延迟指标存储在:")
    print("      - messages.metadata: 每条消息的延迟信息")
    print("      - logs/performance/latency.log: 性能日志")
    print("      - logs/metrics/metrics.log: 业务指标日志")
    
    # 检查是否有延迟数据在消息 metadata 中
    print("\n   🔍 检查消息中的延迟数据:")
    sample_convs = all_conversations[:3] if all_conversations else []
    has_latency_data = False
    
    for conv in sample_convs:
        messages = query_messages(client, conv.get("conversation_id", ""))
        for msg in messages[:5]:
            metadata = msg.get("metadata", {})
            if metadata and isinstance(metadata, dict):
                if "latency" in str(metadata).lower() or "duration" in str(metadata).lower():
                    has_latency_data = True
                    print(f"      ✅ 发现延迟数据: {json.dumps(metadata, ensure_ascii=False)[:200]}")
                    break
        if has_latency_data:
            break
    
    if not has_latency_data:
        print("      ⚠️ 消息 metadata 中未发现明显的延迟指标")
        print("      💡 建议查看 logs/performance/ 目录下的日志文件")
    
    # 4. 数据库表结构概览
    print_section("4. 数据库表结构概览")
    print("   表名           | 用途")
    print("   --------------|----------------------------------")
    print("   users          | 用户信息和画像")
    print("   conversations  | 对话会话")
    print("   messages       | 对话消息")
    print("   assessments    | 评估结果 (如有)")
    print("   learning_reports | 学习报告 (如有)")
    
    print("\n" + "=" * 60)
    print("  查询完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
