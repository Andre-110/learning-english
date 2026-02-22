#!/bin/bash
# 一键安装脚本

set -e

echo "=========================================="
echo "LinguaCoach 安装脚本"
echo "=========================================="
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ 找到: $PYTHON_VERSION"

# 检查并安装pip
if ! command -v pip3 &> /dev/null; then
    echo ""
    echo "⚠️  pip3 未安装，正在安装..."
    sudo apt update
    sudo apt install -y python3-pip
fi

PIP_VERSION=$(pip3 --version)
echo "✅ 找到: $PIP_VERSION"

# 安装依赖
echo ""
echo "安装Python依赖..."
pip3 install -r requirements.txt --user

# 检查关键依赖
echo ""
echo "验证安装..."
python3 -c "import fastapi, uvicorn, openai, pydantic" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ 依赖安装成功"
else
    echo "❌ 依赖安装失败，请检查错误信息"
    exit 1
fi

# 创建.env文件
if [ ! -f .env ]; then
    echo ""
    echo "创建.env文件..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ .env文件已创建"
        echo "⚠️  请编辑.env文件，填入API密钥"
    else
        echo "⚠️  .env.example不存在，请手动创建.env文件"
    fi
else
    echo "✅ .env文件已存在"
fi

echo ""
echo "=========================================="
echo "安装完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 编辑.env文件，填入API密钥"
echo "2. 运行: uvicorn api.main:app --reload"
echo "   或:   ./start.sh"
echo ""





