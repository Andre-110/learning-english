#!/bin/bash
# 虚拟环境设置脚本

set -e

echo "=========================================="
echo "LinguaCoach 虚拟环境设置"
echo "=========================================="
echo ""

# 检查Python版本
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ 找到: $PYTHON_VERSION"

# 检查venv模块
if ! python3 -m venv --help &> /dev/null; then
    echo "❌ venv模块不可用，尝试安装python3-venv"
    sudo apt update
    sudo apt install -y python3-venv
fi

# 创建虚拟环境
if [ -d "venv" ]; then
    echo "⚠️  虚拟环境已存在"
    read -p "是否删除并重新创建? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "删除旧虚拟环境..."
        rm -rf venv
    else
        echo "使用现有虚拟环境"
    fi
fi

if [ ! -d "venv" ]; then
    echo ""
    echo "创建虚拟环境..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建成功"
fi

# 激活虚拟环境
echo ""
echo "激活虚拟环境..."
source venv/bin/activate

# 升级pip
echo ""
echo "升级pip..."
pip install --upgrade pip

# 安装依赖
echo ""
echo "安装项目依赖..."
pip install -r requirements.txt

# 验证安装
echo ""
echo "验证安装..."
python -c "import fastapi, uvicorn, openai, pydantic; print('✅ 所有依赖安装成功')"

# 创建.env文件（如果不存在）
if [ ! -f .env ]; then
    echo ""
    echo "创建.env文件..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ .env文件已创建"
        echo "⚠️  请编辑.env文件，填入API密钥:"
        echo "   OPENAI_API_KEY=your_key_here"
    else
        echo "⚠️  .env.example不存在，请手动创建.env文件"
    fi
else
    echo "✅ .env文件已存在"
fi

echo ""
echo "=========================================="
echo "虚拟环境设置完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 激活虚拟环境: source venv/bin/activate"
echo "2. 编辑.env文件，填入API密钥"
echo "3. 启动服务: uvicorn api.main:app --reload"
echo ""
echo "提示："
echo "- 每次使用前需要激活虚拟环境: source venv/bin/activate"
echo "- 退出虚拟环境: deactivate"
echo ""





