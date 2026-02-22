#!/bin/bash
# 运行所有测试脚本

set -e

echo "=========================================="
echo "运行所有系统测试"
echo "=========================================="
echo ""

cd "$(dirname "$0")/.."
source venv/bin/activate

# 检查服务是否运行
if ! curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "❌ 服务未运行，请先启动服务:"
    echo "   uvicorn api.main:app --reload"
    exit 1
fi

echo "✅ 服务运行正常"
echo ""

# 运行测试
echo "1. API端点测试..."
python test/test_api_integration.py

echo ""
echo "2. 完整系统测试..."
python test/test_full_system.py

echo ""
echo "=========================================="
echo "所有测试完成"
echo "=========================================="





