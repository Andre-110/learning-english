#!/usr/bin/env python3
"""
自动化创建 Supabase 数据库表
尝试多种方法：
1. 通过 psql（如果可用）
2. 通过 Supabase CLI（如果已安装）
3. 生成可直接在 Dashboard 中使用的 SQL
"""
import sys
import os
import subprocess
import getpass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://uxnqqkuviqlptltcepat.supabase.co")
PROJECT_REF = SUPABASE_URL.split("//")[1].split(".")[0] if "//" in SUPABASE_URL else "uxnqqkuviqlptltcepat"

def read_sql_file():
    """读取 SQL 文件"""
    sql_path = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        return f.read()

def method_psql():
    """方法1: 通过 psql 连接"""
    print("\n方法1: 尝试通过 psql 连接...")
    
    if not os.path.exists("/usr/bin/psql") and not os.path.exists("/usr/local/bin/psql"):
        print("  ⚠️  psql 未安装")
        return False
    
    # 获取数据库密码
    db_password = getpass.getpass("请输入 Supabase 数据库密码（可在 Dashboard > Settings > Database 中找到）: ")
    
    if not db_password:
        print("  ❌ 密码不能为空")
        return False
    
    db_url = f"postgresql://postgres:{db_password}@db.{PROJECT_REF}.supabase.co:5432/postgres"
    sql_file = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")
    
    try:
        print("  正在连接数据库...")
        result = subprocess.run(
            ["psql", db_url, "-f", sql_file],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("  ✅ 表创建成功！")
            return True
        else:
            print(f"  ❌ 执行失败: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print("  ❌ 连接超时")
        return False
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return False

def method_supabase_cli():
    """方法2: 通过 Supabase CLI"""
    print("\n方法2: 尝试通过 Supabase CLI...")
    
    if not os.path.exists("/usr/local/bin/supabase") and not os.path.exists(os.path.expanduser("~/.local/bin/supabase")):
        print("  ⚠️  Supabase CLI 未安装")
        print("  安装方法: npm install -g supabase")
        return False
    
    sql_file = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")
    
    try:
        # 需要先链接项目
        print("  注意: Supabase CLI 需要先链接项目")
        print("  运行: supabase link --project-ref " + PROJECT_REF)
        return False
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return False

def method_dashboard():
    """方法3: 生成 Dashboard 使用的 SQL"""
    print("\n方法3: 生成可直接在 Dashboard 中使用的 SQL...")
    
    sql_content = read_sql_file()
    
    output_file = os.path.join(os.path.dirname(__file__), "supabase_schema_for_dashboard.sql")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(sql_content)
    
    print(f"  ✅ SQL 文件已保存到: {output_file}")
    print("\n  请按照以下步骤操作：")
    print("  1. 访问 https://supabase.com/dashboard")
    print("  2. 选择项目")
    print("  3. 进入 SQL Editor")
    print(f"  4. 复制 {output_file} 的内容并执行")
    
    return False  # 这不是自动执行，返回 False

def main():
    """主函数"""
    print("=" * 60)
    print("自动化创建 Supabase 数据库表")
    print("=" * 60)
    
    methods = [
        ("psql", method_psql),
        ("Supabase CLI", method_supabase_cli),
        ("Dashboard", method_dashboard),
    ]
    
    for name, method in methods:
        try:
            if method():
                print(f"\n✅ 通过 {name} 成功创建表！")
                return True
        except KeyboardInterrupt:
            print("\n\n⚠️  用户取消")
            return False
        except Exception as e:
            print(f"  ❌ {name} 方法失败: {e}")
            continue
    
    print("\n" + "=" * 60)
    print("所有自动方法都失败，请使用 Dashboard 手动执行")
    print("=" * 60)
    
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

