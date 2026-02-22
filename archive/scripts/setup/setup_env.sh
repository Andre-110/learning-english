#!/bin/bash
# 快速设置环境变量文件

set -e

echo "=========================================="
echo "环境变量配置"
echo "=========================================="
echo ""

# 检查.env文件是否存在
if [ -f .env ]; then
    echo "⚠️  .env文件已存在"
    read -p "是否覆盖? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消操作"
        exit 0
    fi
fi

# 创建.env文件
if [ -f .env.example ]; then
    cp .env.example .env
    echo "✅ 已从.env.example创建.env文件"
else
    # 如果.env.example不存在，直接创建.env
    cat > .env << 'EOF'
# LLM配置
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# 模型选择
PRIMARY_LLM_MODEL=gpt-4
SECONDARY_LLM_MODEL=gpt-3.5-turbo

# LLM提供商 (openai 或 anthropic)
LLM_PROVIDER=openai

# 系统配置
MAX_CONVERSATION_ROUNDS=20
CONTEXT_SUMMARY_INTERVAL=5
LOG_LEVEL=INFO

# 存储配置
STORAGE_BACKEND=memory
EOF
    echo "✅ 已创建.env文件"
fi

echo ""
echo "=========================================="
echo "下一步：编辑.env文件，填入API密钥"
echo "=========================================="
echo ""
echo "运行以下命令编辑.env文件："
echo "  nano .env"
echo "  或"
echo "  vim .env"
echo ""
echo "重要：将 OPENAI_API_KEY 替换为你的实际API密钥"
echo ""





