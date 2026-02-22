#!/usr/bin/env python3
"""
通过 Supabase REST API 创建数据库表
注意：这需要 service_role key 或通过 Dashboard 手动执行
"""
import sys
import os
import requests
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://uxnqqkuviqlptltcepat.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV4bnFxa3V2aXFscHRsdGNlcGF0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwODIzMDgsImV4cCI6MjA4MDY1ODMwOH0.oI7uVTWBXDnEhRgAsy_L4SZf2vGDpacwfKoEDS1DHsc")

def read_sql_file():
    """读取 SQL 文件"""
    sql_path = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        return f.read()

def split_sql_statements(sql_content):
    """分割 SQL 语句"""
    statements = []
    current_statement = ""
    
    for line in sql_content.split('\n'):
        # 跳过注释
        stripped = line.strip()
        if stripped.startswith('--') or not stripped:
            continue
        
        current_statement += line + '\n'
        
        # 如果行以分号结尾，表示一个完整的语句
        if stripped.endswith(';'):
            statements.append(current_statement.strip())
            current_statement = ""
    
    if current_statement.strip():
        statements.append(current_statement.strip())
    
    return statements

def execute_sql_via_management_api(sql_statements):
    """通过 Management API 执行 SQL"""
    print("=" * 60)
    print("通过 Supabase Management API 创建表")
    print("=" * 60)
    
    # Supabase Management API 端点
    # 注意：这通常需要 service_role key
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    success_count = 0
    fail_count = 0
    
    for idx, sql in enumerate(sql_statements, 1):
        if not sql or len(sql.strip()) < 10:
            continue
        
        print(f"\n[{idx}/{len(sql_statements)}] 执行 SQL...")
        print(f"SQL: {sql[:100]}...")
        
        try:
            # 尝试不同的 API 端点
            endpoints = [
                f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
                f"{SUPABASE_URL}/rest/v1/rpc/execute_sql",
                f"{SUPABASE_URL}/rest/v1/rpc/run_sql",
            ]
            
            executed = False
            for endpoint in endpoints:
                try:
                    payload = {"query": sql}
                    response = requests.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        print(f"  ✅ 成功")
                        success_count += 1
                        executed = True
                        break
                    elif response.status_code == 404:
                        continue  # 尝试下一个端点
                    else:
                        print(f"  ⚠️  状态码: {response.status_code}")
                        print(f"  响应: {response.text[:200]}")
                except requests.exceptions.RequestException as e:
                    continue
            
            if not executed:
                print(f"  ❌ 所有端点都失败")
                fail_count += 1
                
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            fail_count += 1
    
    print("\n" + "=" * 60)
    print(f"执行完成: 成功 {success_count}, 失败 {fail_count}")
    print("=" * 60)
    
    if fail_count > 0:
        print("\n⚠️  由于 Supabase 的安全限制，anon key 无法执行 DDL 操作")
        print("请使用以下方法之一：")
        print("\n方法1: Supabase Dashboard（推荐）")
        print("  1. 访问 https://supabase.com/dashboard")
        print("  2. 选择项目")
        print("  3. 进入 SQL Editor")
        print("  4. 复制并执行 scripts/supabase_schema.sql")
        print("\n方法2: Supabase CLI")
        print("  supabase db push --file scripts/supabase_schema.sql")
    
    return success_count > 0

def main():
    """主函数"""
    sql_content = read_sql_file()
    print(f"✅ 已读取 SQL 文件，共 {len(sql_content)} 字符")
    
    sql_statements = split_sql_statements(sql_content)
    print(f"✅ 已分割为 {len(sql_statements)} 条 SQL 语句")
    
    # 尝试执行
    success = execute_sql_via_management_api(sql_statements)
    
    if not success:
        print("\n" + "=" * 60)
        print("无法通过 API 自动创建表")
        print("=" * 60)
        print("\n请手动执行以下步骤：")
        print("1. 访问 https://supabase.com/dashboard")
        print("2. 选择项目")
        print("3. 进入 SQL Editor")
        print("4. 复制以下 SQL 并执行：")
        print("\n" + "-" * 60)
        print(sql_content)
        print("-" * 60)
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

