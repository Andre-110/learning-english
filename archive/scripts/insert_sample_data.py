#!/usr/bin/env python3
"""
插入模拟数据到 Supabase 数据库
注意：需要先执行 scripts/supabase_schema.sql 创建表结构
"""
import sys
import os
from datetime import datetime, timezone

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client

# Supabase 配置
SUPABASE_URL = "https://uxnqqkuviqlptltcepat.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV4bnFxa3V2aXFscHRsdGNlcGF0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwODIzMDgsImV4cCI6MjA4MDY1ODMwOH0.oI7uVTWBXDnEhRgAsy_L4SZf2vGDpacwfKoEDS1DHsc"


def insert_sample_data():
    """插入模拟数据"""
    print("=" * 60)
    print("插入模拟数据到 Supabase")
    print("=" * 60)
    
    # 创建 Supabase 客户端
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"\n✅ 成功连接到 Supabase: {SUPABASE_URL}")
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        return False
    
    # 1. 创建测试用户
    print("\n1. 创建测试用户...")
    test_users = [
        {
            "user_id": "user_001",
            "username": "alice_student",
            "email": "alice@example.com",
            "overall_score": 65.5,
            "cefr_level": "B1",
            "strengths": ["内容相关性", "语言准确性"],
            "weaknesses": ["交互深度", "词汇丰富度"],
            "conversation_count": 5
        },
        {
            "user_id": "user_002",
            "username": "bob_learner",
            "email": "bob@example.com",
            "overall_score": 42.3,
            "cefr_level": "A2",
            "strengths": ["表达流畅"],
            "weaknesses": ["语言准确性", "词汇丰富度", "交互深度"],
            "conversation_count": 3
        },
        {
            "user_id": "user_003",
            "username": "charlie_beginner",
            "email": "charlie@example.com",
            "overall_score": 28.7,
            "cefr_level": "A1",
            "strengths": ["基本语法正确"],
            "weaknesses": ["词汇有限", "表达深度不足", "句式简单"],
            "conversation_count": 2
        }
    ]
    
    for user in test_users:
        try:
            result = supabase.table("users").insert(user).execute()
            print(f"  ✅ 创建用户: {user['username']} ({user['user_id']})")
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower() or "already exists" in str(e).lower():
                print(f"  ⚠️  用户已存在: {user['username']}")
            else:
                print(f"  ❌ 创建用户失败: {user['username']} - {e}")
    
    # 2. 创建对话会话
    print("\n2. 创建对话会话...")
    conversations = [
        {
            "conversation_id": "conv_001",
            "user_id": "user_001",
            "state": "COMPLETED",
            "current_round": 3,
            "summary": "讨论了日常活动和健康习惯，用户表现出良好的语言基础。"
        },
        {
            "conversation_id": "conv_002",
            "user_id": "user_001",
            "state": "IN_PROGRESS",
            "current_round": 2,
            "summary": None
        },
        {
            "conversation_id": "conv_003",
            "user_id": "user_002",
            "state": "COMPLETED",
            "current_round": 2,
            "summary": "讨论了学习英语的方法和兴趣。"
        }
    ]
    
    for conv in conversations:
        try:
            result = supabase.table("conversations").insert(conv).execute()
            print(f"  ✅ 创建对话: {conv['conversation_id']}")
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                print(f"  ⚠️  对话已存在: {conv['conversation_id']}")
            else:
                print(f"  ❌ 创建对话失败: {conv['conversation_id']} - {e}")
    
    # 3. 创建消息
    print("\n3. 创建消息...")
    messages = [
        {
            "conversation_id": "conv_001",
            "round_number": 1,
            "sender_role": "assistant",
            "content": "Hello! Let's talk about your daily activities. What do you usually do in the morning?",
            "metadata": {}
        },
        {
            "conversation_id": "conv_001",
            "round_number": 1,
            "sender_role": "user",
            "content": "I usually wake up at 7 AM. I brush my teeth and eat breakfast.",
            "metadata": {}
        },
        {
            "conversation_id": "conv_001",
            "round_number": 2,
            "sender_role": "assistant",
            "content": "That sounds like a healthy morning routine! What do you like to do in your free time?",
            "metadata": {}
        },
        {
            "conversation_id": "conv_001",
            "round_number": 2,
            "sender_role": "user",
            "content": "I like reading books and watching movies.",
            "metadata": {}
        }
    ]
    
    for msg in messages:
        try:
            result = supabase.table("messages").insert(msg).execute()
            print(f"  ✅ 创建消息: Round {msg['round_number']}, {msg['sender_role']}")
        except Exception as e:
            print(f"  ❌ 创建消息失败: {e}")
    
    # 4. 创建评估结果
    print("\n4. 创建评估结果...")
    assessments = [
        {
            "conversation_id": "conv_001",
            "user_id": "user_001",
            "round_number": 1,
            "overall_score": 45.5,
            "cefr_level": "A2",
            "strengths": ["表达流畅", "语言准确性"],
            "weaknesses": ["交互深度", "词汇丰富度"],
            "dimension_scores": [
                {"dimension": "内容相关性", "score": 4.0},
                {"dimension": "语言准确性", "score": 4.5},
                {"dimension": "表达流利度", "score": 3.5},
                {"dimension": "交互深度", "score": 2.5},
                {"dimension": "词汇丰富度", "score": 2.0}
            ],
            "raw_llm_response": {}
        },
        {
            "conversation_id": "conv_001",
            "user_id": "user_001",
            "round_number": 2,
            "overall_score": 54.25,
            "cefr_level": "B1",
            "strengths": ["内容相关性", "语言准确性"],
            "weaknesses": ["交互深度", "词汇丰富度"],
            "dimension_scores": [
                {"dimension": "内容相关性", "score": 4.5},
                {"dimension": "语言准确性", "score": 4.0},
                {"dimension": "表达流利度", "score": 3.5},
                {"dimension": "交互深度", "score": 3.0},
                {"dimension": "词汇丰富度", "score": 3.0}
            ],
            "raw_llm_response": {}
        }
    ]
    
    for assessment in assessments:
        try:
            result = supabase.table("assessments").insert(assessment).execute()
            print(f"  ✅ 创建评估: Round {assessment['round_number']}, Score: {assessment['overall_score']}")
        except Exception as e:
            print(f"  ❌ 创建评估失败: {e}")
    
    # 5. 创建学习报告
    print("\n5. 创建学习报告...")
    reports = [
        {
            "user_id": "user_001",
            "conversation_id": "conv_001",
            "report_content": """# 学习报告

## 能力分析
- **当前CEFR等级**：B1（中级水平）
- **综合分数**：54.25/100

## 进步轨迹
- 第1轮：45.5分 (A2)
- 第2轮：54.25分 (B1)

## 强项
- 内容相关性
- 语言准确性

## 弱项
- 交互深度
- 词汇丰富度

## 学习建议
1. 增加词汇量练习
2. 提高对话深度
3. 多练习复杂句式
"""
        }
    ]
    
    for report in reports:
        try:
            result = supabase.table("learning_reports").insert(report).execute()
            print(f"  ✅ 创建报告: User {report['user_id']}")
        except Exception as e:
            print(f"  ❌ 创建报告失败: {e}")
    
    # 6. 创建用户进度
    print("\n6. 创建用户进度...")
    progress_records = [
        {
            "user_id": "user_001",
            "skill_area": "Grammar",
            "topic_area": "Daily Life",
            "latest_score": 54.25,
            "latest_cefr_level": "B1"
        },
        {
            "user_id": "user_001",
            "skill_area": "Vocabulary",
            "topic_area": "Daily Life",
            "latest_score": 45.0,
            "latest_cefr_level": "A2"
        }
    ]
    
    for progress in progress_records:
        try:
            result = supabase.table("user_progress").insert(progress).execute()
            print(f"  ✅ 创建进度: {progress['skill_area']} - {progress['topic_area']}")
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                print(f"  ⚠️  进度已存在: {progress['skill_area']} - {progress['topic_area']}")
            else:
                print(f"  ❌ 创建进度失败: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 模拟数据插入完成")
    print("=" * 60)
    
    # 验证数据
    print("\n验证数据...")
    try:
        users_count = supabase.table("users").select("user_id", count="exact").execute()
        convs_count = supabase.table("conversations").select("conversation_id", count="exact").execute()
        msgs_count = supabase.table("messages").select("message_id", count="exact").execute()
        assessments_count = supabase.table("assessments").select("assessment_id", count="exact").execute()
        
        print(f"  ✅ 用户数: {users_count.count}")
        print(f"  ✅ 对话数: {convs_count.count}")
        print(f"  ✅ 消息数: {msgs_count.count}")
        print(f"  ✅ 评估数: {assessments_count.count}")
    except Exception as e:
        print(f"  ⚠️  验证失败: {e}")
    
    return True


if __name__ == "__main__":
    success = insert_sample_data()
    sys.exit(0 if success else 1)

