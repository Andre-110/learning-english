#!/bin/bash
# 下载测试音频文件的脚本

set -e

echo "=========================================="
echo "下载测试音频文件"
echo "=========================================="
echo ""

AUDIO_DIR="test_audio"
mkdir -p "$AUDIO_DIR"

cd "$AUDIO_DIR"

echo "正在下载测试音频文件..."
echo ""

# 方法1: 使用wget下载一些公开的测试音频
# 注意：这些URL可能需要更新，如果失效请使用其他方法

echo "1. 尝试从公开源下载测试音频..."
echo ""

# 下载一个简单的英语测试音频（如果URL可用）
# 这里使用一些常见的测试音频URL
# 注意：实际使用时可能需要替换为有效的URL

echo "2. 使用文本转语音生成测试音频..."
echo ""

# 检查是否安装了gTTS
if command -v python3 &> /dev/null; then
    echo "   使用gTTS生成测试音频..."
    
    # 生成几个不同难度的测试音频
    python3 << 'EOF'
from gtts import gTTS
import os

# 测试音频1: 简单句子（A1-A2级别）
tts1 = gTTS('I am a student. I like reading books.', lang='en')
tts1.save('test_simple.mp3')
print("   ✅ 生成: test_simple.mp3")

# 测试音频2: 中等难度（B1级别）
tts2 = gTTS('I am a student. I like reading books very much. Reading helps me learn new words and improve my English skills. I read for about 30 minutes every day.', lang='en')
tts2.save('test_medium.mp3')
print("   ✅ 生成: test_medium.mp3")

# 测试音频3: 较难（B2-C1级别）
tts3 = gTTS('As an avid reader, I find that immersing myself in literature not only expands my vocabulary but also enhances my linguistic proficiency. The intricate narratives and sophisticated language structures provide invaluable insights into effective communication.', lang='en')
tts3.save('test_advanced.mp3')
print("   ✅ 生成: test_advanced.mp3")
EOF

    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ 测试音频生成成功！"
    else
        echo ""
        echo "⚠️  gTTS未安装，尝试安装..."
        pip3 install gtts || echo "   安装失败，请手动安装: pip install gtts"
    fi
else
    echo "   ⚠️  Python3未找到"
fi

echo ""
echo "=========================================="
echo "下载完成"
echo "=========================================="
echo ""
echo "测试音频文件位置: $AUDIO_DIR/"
ls -lh *.mp3 2>/dev/null || echo "   未找到音频文件"
echo ""
echo "使用方法:"
echo "  python test/test_listening.py"
echo ""





