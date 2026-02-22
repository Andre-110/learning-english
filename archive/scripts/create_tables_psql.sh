#!/bin/bash
# 通过 psql 直接连接 Supabase 数据库并创建表
# 需要数据库密码

SUPABASE_URL="${SUPABASE_URL:-https://uxnqqkuviqlptltcepat.supabase.co}"
PROJECT_REF=$(echo $SUPABASE_URL | sed 's|https://||' | cut -d'.' -f1)

echo "============================================================"
echo "通过 psql 创建 Supabase 数据库表"
echo "============================================================"
echo ""
echo "项目引用: $PROJECT_REF"
echo ""
echo "需要数据库密码才能连接"
echo "密码可以在 Supabase Dashboard > Settings > Database 中找到"
echo ""
read -sp "请输入数据库密码: " DB_PASSWORD
echo ""

if [ -z "$DB_PASSWORD" ]; then
    echo "❌ 密码不能为空"
    exit 1
fi

DB_URL="postgresql://postgres:${DB_PASSWORD}@db.${PROJECT_REF}.supabase.co:5432/postgres"
SQL_FILE="$(dirname "$0")/supabase_schema.sql"

echo "连接数据库..."
if command -v psql &> /dev/null; then
    psql "$DB_URL" -f "$SQL_FILE"
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ 表创建成功！"
    else
        echo ""
        echo "❌ 表创建失败"
        exit 1
    fi
else
    echo "❌ psql 未安装"
    echo "安装方法: sudo apt install postgresql-client"
    exit 1
fi

