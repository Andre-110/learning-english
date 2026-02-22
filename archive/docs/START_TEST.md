# 启动和测试指南

## 当前配置

✅ API密钥已配置
✅ 模型：gpt-4-turbo
✅ Whisper：whisper-1
✅ 依赖已安装

## 启动服务

### 方式1：前台启动（推荐用于测试）

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 方式2：后台启动

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/lingua_coach.log 2>&1 &
```

查看日志：
```bash
tail -f /tmp/lingua_coach.log
```

停止服务：
```bash
pkill -f "uvicorn api.main:app"
```

## 测试API

### 快速测试脚本

```bash
source venv/bin/activate
python test_quick.py
```

### 手动测试

#### 1. 健康检查
```bash
curl http://localhost:8000/
```

#### 2. 开始对话
```bash
curl -X POST "http://localhost:8000/conversations/start" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user"}'
```

#### 3. 回答问题
```bash
# 替换{conversation_id}为上面返回的ID
curl -X POST "http://localhost:8000/conversations/{conversation_id}/respond" \
  -H "Content-Type: application/json" \
  -d '{"user_response": "I am a student. 我喜欢读书。"}'
```

## 测试语音输入

```bash
# 准备音频文件
curl -X POST "http://localhost:8000/conversations/{conversation_id}/respond-audio" \
  -F "audio_file=@your_audio.mp3"
```

## 查看API文档

访问：http://localhost:8000/docs

## 常见问题

### 服务无法启动
```bash
# 检查端口是否被占用
lsof -i :8000

# 检查日志
tail -f /tmp/lingua_coach.log
```

### API密钥错误
```bash
# 检查.env文件
cat .env | grep OPENAI_API_KEY
```

### 模型不可用
确保使用正确的模型名称：
- gpt-4-turbo ✅
- gpt-4 ✅
- gpt-3.5-turbo ✅

