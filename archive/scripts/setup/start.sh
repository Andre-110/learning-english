#!/bin/bash
# LinguaCoach 启动脚本

echo "=========================================="
echo "LinguaCoach API 服务启动"
echo "=========================================="
echo ""

# 检查.env文件
if [ ! -f .env ]; then
    echo "⚠️  警告: .env文件不存在"
    echo "   正在从.env.example创建..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ 已创建.env文件，请编辑并填入API密钥"
        echo ""
        echo "请编辑.env文件后重新运行此脚本"
        exit 1
    else
        echo "❌ .env.example文件也不存在"
        exit 1
    fi
fi

# 检查Python依赖
echo "检查Python依赖..."
python3 -c "import fastapi, uvicorn, pydantic, openai" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  部分依赖未安装，正在安装..."
    pip install -r requirements.txt
fi

# 运行配置检查
echo ""
echo "运行配置检查..."
python3 scripts/check_config.py
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 配置检查未通过，请修复后重试"
    exit 1
fi

echo ""
echo "=========================================="
echo "启动服务..."
echo "=========================================="
echo ""
echo "服务将在 http://localhost:8000 启动"
echo "API文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 启动服务
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000





