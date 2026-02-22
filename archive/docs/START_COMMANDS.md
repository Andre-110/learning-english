# 服务启动命令

## 🚀 快速启动

### 方式1：使用启动脚本（推荐）

```bash
cd /home/ubuntu/learning_english
./scripts/setup/start.sh
```

### 方式2：手动启动

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 方式3：后台启动

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
```

### 方式4：使用启动并测试脚本

```bash
cd /home/ubuntu/learning_english
./scripts/setup/start_and_test.sh
```

## 📋 完整启动流程

### 1. 进入项目目录

```bash
cd /home/ubuntu/learning_english
```

### 2. 激活虚拟环境

```bash
source venv/bin/activate
```

### 3. 启动服务

```bash
# 前台运行（可以看到实时日志）
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# 或后台运行（日志输出到文件）
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
```

## 🔍 检查服务状态

### 检查进程

```bash
pgrep -f "uvicorn api.main:app"
```

### 检查端口

```bash
netstat -tlnp | grep 8000
# 或
lsof -i :8000
```

### 测试API

```bash
# 使用Python测试
python3 -c "import requests; print(requests.get('http://localhost:8000/api').json())"

# 或使用curl（如果已安装）
curl http://localhost:8000/api
```

## 🛑 停止服务

### 方式1：如果在前台运行

按 `Ctrl+C` 停止

### 方式2：停止后台进程

```bash
# 查找进程ID
pgrep -f "uvicorn api.main:app"

# 停止进程
pkill -f "uvicorn api.main:app"

# 或使用kill命令
kill $(pgrep -f "uvicorn api.main:app")
```

## 📝 查看日志

### 实时查看日志

```bash
tail -f /tmp/uvicorn.log
```

### 查看最近日志

```bash
tail -100 /tmp/uvicorn.log
```

## 🌐 访问地址

启动成功后，可以通过以下地址访问：

- **前端页面**: http://localhost:8000/
- **API端点**: http://localhost:8000/api
- **WebSocket**: ws://localhost:8000/streaming-voice/{conversation_id}/chat

## ⚙️ 启动参数说明

```bash
python -m uvicorn api.main:app \
    --host 0.0.0.0 \      # 监听所有网络接口
    --port 8000 \         # 端口号
    --reload \            # 开发模式：代码变更自动重载（可选）
    --workers 1           # 工作进程数（可选）
```

## 🔧 常见问题

### 1. 端口被占用

```bash
# 检查端口占用
lsof -i :8000

# 停止占用端口的进程
kill -9 $(lsof -t -i:8000)
```

### 2. 虚拟环境未激活

```bash
# 确保激活虚拟环境
source venv/bin/activate

# 检查Python路径
which python
# 应该显示: /home/ubuntu/learning_english/venv/bin/python
```

### 3. 依赖未安装

```bash
# 安装依赖
pip install -r requirements.txt
```

### 4. 配置文件缺失

```bash
# 检查.env文件
ls -la .env

# 如果不存在，需要创建并配置
cp .env.example .env  # 如果有示例文件
# 然后编辑.env文件，填入必要的配置
```

## 📚 相关文档

- 项目结构：`docs/PROJECT_STRUCTURE.md`
- 快速开始：`docs/QUICK_START.md`
- 系统逻辑：`docs/SYSTEM_LOGIC.md`





