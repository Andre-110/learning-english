#!/usr/bin/env python3
"""
设置 Supabase 数据库：创建表结构和插入模拟数据
"""
import sys
import os
from datetime import datetime, timezone
import uuid

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client, Client
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Supabase 配置
SUPABASE_URL = "https://uxnqqkuviqlptltcepat.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV4bnFxa3V2aXFscHRsdGNlcGF0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwODIzMDgsImV4cCI6MjA4MDY1ODMwOH0.oI7uVTWBXDnEhRgAsy_L4SZf2vGDpacwfKoEDS1DHsc"


def create_tables(supabase: Client):
    """创建数据库表"""
    print("=" * 60)
    print("创建数据库表")
    print("=" * 60)
    
    # SQL 语句（PostgreSQL 兼容）
    sql_statements = [
        # 1. 用户表
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(255) PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_login_at TIMESTAMPTZ DEFAULT NOW(),
            
            -- 能力画像字段
            overall_score REAL DEFAULT 0.0,
            cefr_level VARCHAR(10) DEFAULT 'A1',
            strengths JSONB DEFAULT '[]',
            weaknesses JSONB DEFAULT '[]',
            conversation_count INT DEFAULT 0,
            
            -- 其他元数据
            metadata JSONB DEFAULT '{}'
        );
        """,
        
        # 2. 对话会话表
        """
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            started_at TIMESTAMPTZ DEFAULT NOW(),
            ended_at TIMESTAMPTZ,
            state VARCHAR(50) DEFAULT 'IN_PROGRESS',
            current_round INT DEFAULT 0,
            summary TEXT,
            summary_round INT DEFAULT 0,
            
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """,
        
        # 3. 对话消息表
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id SERIAL PRIMARY KEY,
            conversation_id VARCHAR(255) NOT NULL,
            round_number INT NOT NULL,
            sender_role VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            metadata JSONB DEFAULT '{}',
            
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
        );
        """,
        
        # 4. 评估结果表
        """
        CREATE TABLE IF NOT EXISTS assessments (
            assessment_id SERIAL PRIMARY KEY,
            conversation_id VARCHAR(255) NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            round_number INT NOT NULL,
            overall_score REAL NOT NULL,
            cefr_level VARCHAR(10) NOT NULL,
            strengths JSONB DEFAULT '[]',
            weaknesses JSONB DEFAULT '[]',
            dimension_scores JSONB DEFAULT '[]',
            raw_llm_response JSONB DEFAULT '{}',
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """,
        
        # 5. 学习报告表
        """
        CREATE TABLE IF NOT EXISTS learning_reports (
            report_id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            conversation_id VARCHAR(255),
            generated_at TIMESTAMPTZ DEFAULT NOW(),
            report_content TEXT NOT NULL,
            
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE SET NULL
        );
        """,
        
        # 6. 音频文件表
        """
        CREATE TABLE IF NOT EXISTS audio_files (
            audio_id SERIAL PRIMARY KEY,
            message_id INT UNIQUE,
            file_path VARCHAR(512) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_size_bytes BIGINT,
            mime_type VARCHAR(100),
            uploaded_at TIMESTAMPTZ DEFAULT NOW(),
            
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE SET NULL
        );
        """,
        
        # 7. 用户学习进度表
        """
        CREATE TABLE IF NOT EXISTS user_progress (
            progress_id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            skill_area VARCHAR(255),
            topic_area VARCHAR(255),
            latest_score REAL,
            latest_cefr_level VARCHAR(10),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            UNIQUE (user_id, skill_area, topic_area)
        );
        """,
    ]
    
    # 创建索引
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_users_cefr_level ON users (cefr_level);",
        "CREATE INDEX IF NOT EXISTS idx_users_overall_score ON users (overall_score);",
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations (user_id);",
        "CREATE INDEX IF NOT EXISTS idx_conversations_state ON conversations (state);",
        "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_messages_round_number ON messages (conversation_id, round_number);",
        "CREATE INDEX IF NOT EXISTS idx_assessments_conversation_id ON assessments (conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_assessments_user_id ON assessments (user_id);",
        "CREATE INDEX IF NOT EXISTS idx_assessments_round_number ON assessments (conversation_id, round_number);",
        "CREATE INDEX IF NOT EXISTS idx_learning_reports_user_id ON learning_reports (user_id);",
        "CREATE INDEX IF NOT EXISTS idx_audio_files_message_id ON audio_files (message_id);",
        "CREATE INDEX IF NOT EXISTS idx_user_progress_user_id ON user_progress (user_id);",
    ]
    
    # 注意：Supabase 使用 PostgreSQL，需要通过 SQL 编辑器或 REST API 执行 SQL
    # 这里我们使用 Python 客户端来创建表（如果支持）或提供 SQL 脚本
    
    print("\n⚠️  注意：Supabase 需要通过 SQL 编辑器创建表")
    print("请将以下 SQL 语句复制到 Supabase Dashboard > SQL Editor 中执行：\n")
    
    print("--" + "=" * 58)
    print("-- 创建表的 SQL 语句")
    print("--" + "=" * 58)
    for sql in sql_statements:
        print(sql)
    
    print("\n--" + "=" * 58)
    print("-- 创建索引的 SQL 语句")
    print("--" + "=" * 58)
    for sql in index_statements:
        print(sql)
    
    return True


def insert_sample_data(supabase: Client):
    """插入模拟数据"""
    print("\n" + "=" * 60)
    print("插入模拟数据")
    print("=" * 60)
    
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
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
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
            if "duplicate" in str(e).lower():
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
            if "duplicate" in str(e).lower():
                print(f"  ⚠️  进度已存在: {progress['skill_area']} - {progress['topic_area']}")
            else:
                print(f"  ❌ 创建进度失败: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 模拟数据插入完成")
    print("=" * 60)


def main():
    """主函数"""
    print("=" * 60)
    print("Supabase 数据库设置")
    print("=" * 60)
    
    # 创建 Supabase 客户端
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"\n✅ 成功连接到 Supabase: {SUPABASE_URL}")
        
        # 测试连接
        try:
            # 尝试查询 users 表（如果存在）
            result = supabase.table("users").select("user_id").limit(1).execute()
            print("  ✅ 数据库连接正常")
        except Exception as e:
            if "relation" in str(e).lower() or "does not exist" in str(e).lower():
                print("  ⚠️  表尚未创建，需要先执行 SQL 脚本")
            else:
                print(f"  ⚠️  连接测试: {e}")
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 创建表（输出 SQL 脚本）
    create_tables(supabase)
    
    # 询问是否插入数据
    print("\n" + "=" * 60)
    response = input("是否现在插入模拟数据？(y/n): ").strip().lower()
    
    if response == 'y':
        try:
            insert_sample_data(supabase)
            return True
        except Exception as e:
            print(f"\n❌ 插入数据失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print("\n跳过数据插入。")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

