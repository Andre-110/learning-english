#!/usr/bin/env python3
"""
尝试通过 Supabase Management API 执行 SQL
注意：这需要 service_role key，anon key 通常没有权限
"""
import sys
import os
import requests
import json

SUPABASE_URL = "https://uxnqqkuviqlptltcepat.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV4bnFxa3V2aXFscHRsdGNlcGF0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwODIzMDgsImV4cCI6MjA4MDY1ODMwOH0.oI7uVTWBXDnEhRgAsy_L4SZf2vGDpacwfKoEDS1DHsc"

def read_sql_file():
    """读取 SQL 文件"""
    sql_path = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        return f.read()

def execute_sql_via_rest_api(sql: str):
    """尝试通过 REST API 执行 SQL"""
    # Supabase 的 REST API 端点
    # 注意：anon key 通常没有执行 DDL 的权限
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "query": sql
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text[:500]}")
        return response.status_code == 200
    except Exception as e:
        print(f"错误: {e}")
        return False

def main():
    print("=" * 60)
    print("通过 Supabase API 执行 SQL")
    print("=" * 60)
    
    sql_content = read_sql_file()
    print(f"\n✅ 已读取 SQL 文件，共 {len(sql_content)} 字符")
    
    # 尝试执行（可能会失败，因为 anon key 没有 DDL 权限）
    print("\n⚠️  尝试通过 REST API 执行 SQL...")
    print("注意：anon key 通常没有执行 DDL 的权限")
    
    success = execute_sql_via_rest_api(sql_content)
    
    if not success:
        print("\n" + "=" * 60)
        print("❌ API 执行失败（这是预期的，anon key 没有 DDL 权限）")
        print("=" * 60)
        print("\n📝 请手动执行 SQL：")
        print("1. 登录 https://supabase.com/dashboard")
        print("2. 选择项目")
        print("3. 进入 SQL Editor")
        print("4. 复制以下 SQL 并执行：")
        print("\n" + "-" * 60)
        print(sql_content)
        print("-" * 60)
        return False
    
    print("\n✅ SQL 执行成功！")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

