#!/bin/bash
# Conda安装脚本

set -e

echo "=========================================="
echo "Conda安装脚本"
echo "=========================================="
echo ""

# 检查是否已安装conda
if command -v conda &> /dev/null; then
    echo "✅ Conda已安装: $(conda --version)"
    exit 0
fi

echo "Conda未安装，开始安装Miniconda..."
echo ""

# 检测系统架构
ARCH=$(uname -m)
if [ "$ARCH" == "x86_64" ]; then
    ARCH="x86_64"
elif [ "$ARCH" == "aarch64" ]; then
    ARCH="aarch64"
else
    echo "❌ 不支持的架构: $ARCH"
    exit 1
fi

# Miniconda下载URL
MINICONDA_VERSION="latest"
MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-${MINICONDA_VERSION}-Linux-${ARCH}.sh"

echo "下载Miniconda..."
echo "URL: $MINICONDA_URL"
echo ""

# 下载Miniconda
INSTALLER="/tmp/miniconda.sh"
wget -q $MINICONDA_URL -O $INSTALLER

if [ ! -f "$INSTALLER" ]; then
    echo "❌ 下载失败"
    exit 1
fi

echo "✅ 下载完成"
echo ""

# 安装Miniconda
echo "安装Miniconda..."
bash $INSTALLER -b -p $HOME/miniconda3

# 初始化conda
echo ""
echo "初始化Conda..."
$HOME/miniconda3/bin/conda init bash

# 添加到PATH
export PATH="$HOME/miniconda3/bin:$PATH"

echo ""
echo "=========================================="
echo "Conda安装完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 重新加载shell配置:"
echo "   source ~/.bashrc"
echo ""
echo "2. 验证安装:"
echo "   conda --version"
echo ""
echo "3. 创建项目环境:"
echo "   conda env create -f environment.yml"
echo "   conda activate lingua_coach"
echo ""
echo "注意：如果使用zsh，运行: conda init zsh && source ~/.zshrc"
echo ""

# 清理安装文件
rm -f $INSTALLER





