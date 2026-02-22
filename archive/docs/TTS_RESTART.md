# TTS 服务重启说明

## 问题

TTS API 返回 500 错误：`Can't patch loop of type <class 'uvloop.Loop'>`

这是因为服务器需要重启以加载修复后的代码。

## 解决方案

### 方法1：重启服务器（推荐）

```bash
# 1. 停止当前服务器
pkill -f 'uvicorn api.main:app'

# 2. 启动服务器（带热重载）
cd /home/ubuntu/learning_english
source venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 方法2：使用后台运行（生产环境）

```bash
# 停止服务器
pkill -f 'uvicorn api.main:app'

# 后台启动
cd /home/ubuntu/learning_english
source venv/bin/activate
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
```

## 验证

重启后，运行测试脚本：

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
python3 test/test_tts_api.py
```

## 直接测试 TTS 服务（不通过 API）

如果不想重启服务器，可以直接测试 TTS 服务：

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
python3 test/test_tts_direct.py
```

