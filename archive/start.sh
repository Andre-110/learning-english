#!/bin/bash
# LinguaCoach 启动脚本
# 自动清理端口并启动服务

PORT=8000

echo "🔍 检查端口 $PORT 是否被占用..."

# 查找占用端口的进程
PID=$(lsof -ti:$PORT 2>/dev/null)

if [ -n "$PID" ]; then
    echo "⚠️  端口 $PORT 被进程 $PID 占用，正在终止..."
    kill -9 $PID 2>/dev/null
    sleep 1
    echo "✅ 进程已终止"
else
    echo "✅ 端口 $PORT 空闲"
fi

echo "🚀 启动 LinguaCoach 服务..."
cd /home/ubuntu/learning_english

# 激活虚拟环境
source venv/bin/activate

python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT --reload

