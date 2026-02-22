#!/bin/bash
# Conda虚拟环境设置脚本

set -e

echo "=========================================="
echo "LinguaCoach Conda环境设置"
echo "=========================================="
echo ""

# 检查conda是否安装
if ! command -v conda &> /dev/null; then
    echo "❌ Conda未安装"
    echo ""
    echo "请先安装Conda:"
    echo "1. Miniconda: https://docs.conda.io/en/latest/miniconda.html"
    echo "2. Anaconda: https://www.anaconda.com/products/distribution"
    exit 1
fi

CONDA_VERSION=$(conda --version)
echo "✅ 找到: $CONDA_VERSION"

# 检查conda环境是否已存在
ENV_NAME="lingua_coach"
if conda env list | grep -q "^${ENV_NAME} "; then
    echo "⚠️  环境 ${ENV_NAME} 已存在"
    read -p "是否删除并重新创建? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "删除旧环境..."
        conda env remove -n ${ENV_NAME} -y
    else
        echo "使用现有环境"
        echo "激活环境: conda activate ${ENV_NAME}"
        exit 0
    fi
fi

# 创建conda环境
echo ""
echo "创建Conda环境: ${ENV_NAME}..."
conda create -n ${ENV_NAME} python=3.9 -y

# 激活环境
echo ""
echo "激活环境..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ${ENV_NAME}

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
echo "Conda环境设置完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 激活环境: conda activate ${ENV_NAME}"
echo "2. 编辑.env文件，填入API密钥"
echo "3. 启动服务: uvicorn api.main:app --reload"
echo ""
echo "提示："
echo "- 激活环境: conda activate ${ENV_NAME}"
echo "- 退出环境: conda deactivate"
echo "- 查看环境列表: conda env list"
echo "- 删除环境: conda env remove -n ${ENV_NAME}"
echo ""





