#!/bin/bash
# LinguaCoach 服务启动脚本

cd "$(dirname "$0")"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 虚拟环境不存在，请先创建虚拟环境"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 停止旧服务
echo "🛑 停止旧服务..."
pkill -f 'uvicorn api.main:app' 2>/dev/null
sleep 2

# 启动服务
echo "🚀 启动服务..."
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
echo $! > /tmp/uvicorn.pid

# 等待服务启动
sleep 3

# 检查服务状态
if ps -p $(cat /tmp/uvicorn.pid) > /dev/null 2>&1; then
    echo "✅ 服务已启动 (PID: $(cat /tmp/uvicorn.pid))"
    echo ""
    echo "📋 访问地址:"
    echo "  - 前端: http://localhost:8000/"
    echo "  - API文档: http://localhost:8000/docs"
    echo "  - API: http://localhost:8000/api"
    echo ""
    echo "📝 查看日志:"
    echo "  tail -f /tmp/uvicorn.log"
    echo ""
    echo "🛑 停止服务:"
    echo "  pkill -f 'uvicorn api.main:app'"
    echo "  或"
    echo "  kill $(cat /tmp/uvicorn.pid)"
else
    echo "❌ 服务启动失败，请查看日志:"
    echo "  tail -50 /tmp/uvicorn.log"
    exit 1
fi










