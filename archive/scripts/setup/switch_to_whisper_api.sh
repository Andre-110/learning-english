#!/bin/bash
# 切换到Whisper API的脚本

echo "=========================================="
echo "切换到 Whisper API"
echo "=========================================="

# 检查.env文件
if [ ! -f .env ]; then
    echo "❌ .env 文件不存在"
    exit 1
fi

# 备份.env文件
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
echo "✓ 已备份 .env 文件"

# 检查OPENAI_API_KEY
if ! grep -q "OPENAI_API_KEY=" .env || grep -q "OPENAI_API_KEY=$" .env; then
    echo "⚠️  警告: OPENAI_API_KEY 未设置或为空"
    echo "请在 .env 文件中设置有效的 OPENAI_API_KEY"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 修改配置
echo ""
echo "修改配置..."

# 设置SPEECH_PROVIDER为whisper
if grep -q "SPEECH_PROVIDER=" .env; then
    sed -i 's/^SPEECH_PROVIDER=.*/SPEECH_PROVIDER=whisper/' .env
else
    echo "SPEECH_PROVIDER=whisper" >> .env
fi
echo "✓ 设置 SPEECH_PROVIDER=whisper"

# 注释掉OPENAI_BASE_URL（使用官方API）
if grep -q "OPENAI_BASE_URL=" .env; then
    sed -i 's/^OPENAI_BASE_URL=/#OPENAI_BASE_URL=/' .env
    echo "✓ 已注释 OPENAI_BASE_URL（使用官方OpenAI API）"
fi

echo ""
echo "=========================================="
echo "配置已更新"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 确保 .env 文件中有有效的 OPENAI_API_KEY"
echo "2. 重启后端服务："
echo "   pkill -f 'uvicorn api.main:app'"
echo "   python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "3. 测试性能："
echo "   python3 test/test_stt_performance.py"
echo ""



