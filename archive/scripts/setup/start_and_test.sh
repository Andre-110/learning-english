#!/bin/bash
# 启动服务并测试性能

echo "=========================================="
echo "启动服务并测试性能"
echo "=========================================="

# 获取脚本所在目录，然后回到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# 检查服务是否已运行
if pgrep -f "uvicorn api.main:app" > /dev/null; then
    echo "✓ 服务已在运行"
    PID=$(pgrep -f "uvicorn api.main:app" | head -1)
    echo "  进程ID: $PID"
else
    echo "启动服务..."
    source venv/bin/activate
    
    # 在后台启动服务
    nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
    PID=$!
    echo "✓ 服务已启动，进程ID: $PID"
    echo "  日志文件: /tmp/uvicorn.log"
    
    # 等待服务启动
    echo "等待服务启动（最多30秒）..."
    for i in {1..30}; do
        sleep 1
        if python3 -c "import requests; requests.get('http://localhost:8000/api', timeout=1)" 2>/dev/null; then
            echo "✓ 服务已就绪（${i}秒）"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "❌ 服务启动超时"
            exit 1
        fi
    done
fi

echo ""
echo "=========================================="
echo "服务信息"
echo "=========================================="
echo "访问地址: http://localhost:8000/"
echo "API地址: http://localhost:8000/api"
echo "WebSocket: ws://localhost:8000/streaming-voice/{conversation_id}/chat"
echo ""

# 运行性能测试
echo "=========================================="
echo "运行性能测试"
echo "=========================================="
python3 test/test_frontend_performance.py

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
echo ""
echo "现在可以："
echo "1. 打开浏览器访问 http://localhost:8000/"
echo "2. 点击'开始性能测试'按钮"
echo "3. 进行录音，查看实时性能数据"
echo ""
echo "查看服务日志: tail -f /tmp/uvicorn.log"


