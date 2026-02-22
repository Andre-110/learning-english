# 服务启动指南

## 🚀 快速启动

### 方式一：使用启动脚本（推荐）

```bash
cd /home/ubuntu/learning_english
./start_server.sh
```

### 方式二：直接命令启动

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
echo $! > /tmp/uvicorn.pid
```

### 方式三：开发模式（带热重载）

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

## 📋 服务管理命令

### 启动服务

```bash
# 后台启动
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
echo $! > /tmp/uvicorn.pid

# 或使用启动脚本
./start_server.sh
```

### 查看服务状态

```bash
# 查看进程
ps aux | grep uvicorn | grep -v grep

# 查看PID文件
cat /tmp/uvicorn.pid

# 测试服务是否运行
curl http://localhost:8000/api
```

### 查看日志

```bash
# 实时查看日志
tail -f /tmp/uvicorn.log

# 查看最后50行
tail -50 /tmp/uvicorn.log

# 查看错误日志
grep ERROR /tmp/uvicorn.log
```

### 停止服务

```bash
# 方式一：使用PID文件
kill $(cat /tmp/uvicorn.pid)

# 方式二：使用进程名
pkill -f 'uvicorn api.main:app'

# 方式三：强制停止
pkill -9 -f 'uvicorn api.main:app'
```

### 重启服务

```bash
# 停止并重启
pkill -f 'uvicorn api.main:app' && sleep 2 && \
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 & \
echo $! > /tmp/uvicorn.pid

# 或使用启动脚本
./start_server.sh
```

## 🌐 访问地址

启动成功后，可以通过以下地址访问：

- **前端界面**: http://localhost:8000/
- **API文档**: http://localhost:8000/docs
- **API根路径**: http://localhost:8000/api
- **认证API**: http://localhost:8000/auth/

## ⚙️ 启动参数说明

### 基本参数

- `--host 0.0.0.0`: 监听所有网络接口（允许外部访问）
- `--port 8000`: 服务端口号
- `--reload`: 开发模式，代码变更自动重启

### 生产环境参数

- `--workers 4`: 工作进程数（根据CPU核心数调整）
- `--log-level info`: 日志级别（debug/info/warning/error）
- `--access-log`: 启用访问日志

### 完整启动命令示例

```bash
# 生产环境（4个工作进程）
uvicorn api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info \
  --access-log

# 开发环境（带热重载）
uvicorn api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --log-level debug
```

## 🔍 故障排查

### 服务无法启动

1. 检查端口是否被占用：
   ```bash
   lsof -i :8000
   netstat -tulpn | grep 8000
   ```

2. 检查虚拟环境是否激活：
   ```bash
   which python
   # 应该显示 venv/bin/python
   ```

3. 检查依赖是否安装：
   ```bash
   pip list | grep uvicorn
   ```

4. 查看错误日志：
   ```bash
   tail -100 /tmp/uvicorn.log
   ```

### 服务启动但无法访问

1. 检查防火墙设置：
   ```bash
   sudo ufw status
   ```

2. 检查服务是否监听正确端口：
   ```bash
   netstat -tulpn | grep 8000
   ```

3. 检查服务日志：
   ```bash
   tail -50 /tmp/uvicorn.log
   ```

## 📝 注意事项

1. **首次启动**：FunASR模型加载需要20-30秒，请耐心等待
2. **内存要求**：建议至少2GB可用内存
3. **端口占用**：确保8000端口未被其他服务占用
4. **日志文件**：日志文件位于 `/tmp/uvicorn.log`，注意定期清理

## 🔐 环境变量

确保以下环境变量已正确设置（在 `.env` 文件中）：

- `OPENAI_API_KEY`: OpenAI API密钥
- `SUPABASE_URL`: Supabase数据库URL
- `SUPABASE_KEY`: Supabase API密钥
- `JWT_SECRET_KEY`: JWT密钥（生产环境必须修改）

## 📚 相关文档

- [API文档](http://localhost:8000/docs) - 启动后访问
- [存储概览](../docs/STORAGE_OVERVIEW.md) - 数据存储说明
- [系统逻辑](../docs/SYSTEM_LOGIC.md) - 系统架构说明





