#!/bin/bash
# FunASR部署脚本

set -e

echo "=========================================="
echo "FunASR本地部署脚本"
echo "=========================================="

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# 检查虚拟环境
if [ -d "$PROJECT_DIR/venv" ]; then
    echo "✅ 检测到虚拟环境: $PROJECT_DIR/venv"
    source "$PROJECT_DIR/venv/bin/activate"
    echo "✅ 已激活虚拟环境"
elif [ -n "$VIRTUAL_ENV" ]; then
    echo "✅ 已在虚拟环境中: $VIRTUAL_ENV"
else
    echo "⚠️  未检测到虚拟环境，尝试创建..."
    python3 -m venv "$PROJECT_DIR/venv"
    source "$PROJECT_DIR/venv/bin/activate"
    echo "✅ 已创建并激活虚拟环境"
fi

# 检查Python环境
if ! command -v python &> /dev/null; then
    echo "❌ Python未安装"
    exit 1
fi

echo "✅ Python版本: $(python --version)"
echo "✅ Python路径: $(which python)"

# 检查pip
if ! command -v pip &> /dev/null; then
    echo "❌ pip未安装"
    exit 1
fi

echo "✅ pip版本: $(pip --version)"

# 升级pip
echo ""
echo "正在升级pip..."
pip install --upgrade pip -q

# 安装FunASR依赖
echo ""
echo "正在安装FunASR依赖..."
pip install funasr==1.1.12 modelscope==1.15.0

# 检查PyTorch
echo ""
echo "检查PyTorch安装..."
python -c "import torch; print(f'✅ PyTorch版本: {torch.__version__}')" 2>/dev/null || {
    echo "⚠️  PyTorch未安装，正在安装CPU版本..."
    pip install torch torchvision torchaudio
}

# 测试FunASR导入
echo ""
echo "测试FunASR导入..."
python -c "from funasr import AutoModel; print('✅ FunASR导入成功')" || {
    echo "❌ FunASR导入失败"
    exit 1
}

# 测试模型加载（可选）
echo ""
read -p "是否测试模型加载？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "正在测试模型加载（首次会下载模型，可能需要几分钟）..."
    python << 'EOF'
from funasr import AutoModel
import os

model_name = os.getenv("FUNASR_MODEL_NAME", "iic/SenseVoiceSmall")
print(f"使用模型: {model_name}")

try:
    model = AutoModel(model=model_name, trust_remote_code=True)
    print("✅ 模型加载成功！")
except Exception as e:
    print(f"❌ 模型加载失败: {e}")
    exit(1)
EOF
fi

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 在.env文件中配置: SPEECH_PROVIDER=funasr"
echo "2. 运行测试: python test/test_funasr_deployment.py"
echo "3. 启动服务: uvicorn api.main:app --reload"

