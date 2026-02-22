#!/usr/bin/env python3
"""
生成可直接在 Supabase Dashboard 中执行的 SQL
由于网络限制无法直接连接数据库，提供一键复制功能
"""
import sys
import os
import pyperclip

def read_sql_file():
    """读取 SQL 文件"""
    sql_path = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        return f.read()

def main():
    """主函数"""
    print("=" * 60)
    print("Supabase 数据库表创建助手")
    print("=" * 60)
    
    sql_content = read_sql_file()
    
    print(f"\n✅ 已读取 SQL 文件，共 {len(sql_content)} 字符")
    print(f"   包含 {len([s for s in sql_content.split(';') if s.strip()])} 条 SQL 语句")
    
    print("\n" + "=" * 60)
    print("SQL 脚本内容（可直接复制）:")
    print("=" * 60)
    print("\n" + sql_content)
    print("\n" + "=" * 60)
    
    # 尝试复制到剪贴板
    try:
        pyperclip.copy(sql_content)
        print("\n✅ SQL 已复制到剪贴板！")
        print("   可以直接在 Supabase Dashboard 中粘贴执行")
    except:
        print("\n⚠️  无法复制到剪贴板（可能需要安装 pyperclip）")
        print("   请手动复制上面的 SQL 内容")
    
    print("\n📝 执行步骤：")
    print("1. 访问 https://supabase.com/dashboard")
    print("2. 选择项目")
    print("3. 进入 SQL Editor")
    print("4. 点击 'New query'")
    print("5. 粘贴上面的 SQL（已复制到剪贴板）")
    print("6. 点击 'Run' 或按 Ctrl+Enter 执行")
    print("\n✅ 执行完成后，运行以下命令测试：")
    print("   python3 test/test_supabase_integration.py")
    
    # 保存到文件
    output_file = os.path.join(os.path.dirname(__file__), "supabase_schema_for_dashboard.sql")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(sql_content)
    
    print(f"\n📄 SQL 文件已保存到: {output_file}")
    
    return True

if __name__ == "__main__":
    try:
        main()
    except ImportError:
        print("安装 pyperclip: pip install pyperclip")
        # 即使没有 pyperclip 也继续执行
        main()

