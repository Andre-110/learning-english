# 实时语音输入模块集成说明

## 📋 概述

已成功将实时语音输入功能集成到英语学习测评系统中。该模块参考了 `/home/ubuntu/ASR-LLM-TTS/` 目录下的实时语音交互实现，提供了基于WebSocket的实时语音输入能力。

## 🎯 功能特性

### 1. 实时语音录制
- 使用 `PyAudio` 进行实时音频采集
- 支持16kHz采样率，单声道录音
- 可配置的音频块大小和缓冲区

### 2. VAD（语音活动检测）
- 集成 `WebRTC VAD` 进行语音活动检测
- 自动检测语音段和静音段
- 可配置的VAD敏感度和激活阈值

### 3. 自动分段
- 当检测到静音超过阈值时自动保存语音段
- 避免重复处理重叠的语音段
- 自动触发转录和评估流程

### 4. WebSocket实时通信
- 支持WebSocket双向通信
- 实时发送转录结果和评估反馈
- 支持开始/停止监听控制

## 📁 文件结构

```
learning_english/
├── services/
│   ├── speech.py                    # 原有语音服务（Whisper API）
│   └── realtime_speech.py           # 新增：实时语音录制和VAD服务
├── api/
│   ├── speech_endpoint.py           # 原有：文件上传语音端点
│   └── realtime_speech_endpoint.py  # 新增：WebSocket实时语音端点
└── requirements.txt                 # 已更新：添加pyaudio和webrtcvad
```

## 🔧 核心组件

### 1. RealtimeSpeechRecorder
**位置**: `services/realtime_speech.py`

负责实时音频录制和VAD检测：

```python
from services.realtime_speech import RealtimeSpeechRecorder

recorder = RealtimeSpeechRecorder(
    sample_rate=16000,      # 采样率
    channels=1,             # 单声道
    vad_mode=3,             # VAD敏感度（0-3）
    no_speech_threshold=1.0 # 无语音阈值（秒）
)

# 开始录音
recorder.start_recording(on_speech_segment=callback_function)

# 停止录音
recorder.stop_recording()
```

### 2. RealtimeSpeechService
**位置**: `services/realtime_speech.py`

集成录音、VAD和ASR的完整服务：

```python
from services.realtime_speech import create_realtime_speech_service

service = create_realtime_speech_service()

# 开始监听
service.start_listening(on_transcription=lambda text: print(text))

# 停止监听
service.stop_listening()
```

### 3. WebSocket API端点
**位置**: `api/realtime_speech_endpoint.py`

**端点**: `ws://localhost:8000/realtime-speech/{conversation_id}/listen`

**消息格式**:

**客户端 -> 服务端**:
```json
{"type": "start"}  // 开始监听
{"type": "stop"}   // 停止监听
{"type": "close"}  // 关闭连接
```

**服务端 -> 客户端**:
```json
// 连接成功
{"type": "connected", "message": "...", "conversation_id": "..."}

// 监听状态
{"type": "listening_started", "message": "..."}
{"type": "listening_stopped", "message": "..."}

// 转录结果
{"type": "transcription", "text": "...", "normalized_text": "..."}

// 评估结果
{
    "type": "assessment",
    "data": {
        "assessment": {...},
        "user_profile": {...},
        "next_question": "...",
        "round_number": 1
    }
}

// 错误
{"type": "error", "message": "..."}
```

## 🚀 使用示例

### Python客户端示例

```python
import asyncio
import websockets
import json

async def test_realtime_speech():
    uri = "ws://localhost:8000/realtime-speech/{conversation_id}/listen"
    
    async with websockets.connect(uri) as websocket:
        # 接收连接确认
        response = await websocket.recv()
        print(f"连接: {json.loads(response)}")
        
        # 开始监听
        await websocket.send(json.dumps({"type": "start"}))
        response = await websocket.recv()
        print(f"监听状态: {json.loads(response)}")
        
        # 等待转录和评估结果
        while True:
            try:
                response = await websocket.recv()
                data = json.loads(response)
                
                if data["type"] == "transcription":
                    print(f"转录: {data['text']}")
                
                elif data["type"] == "assessment":
                    print(f"评估: {data['data']['assessment']}")
                    print(f"下一题: {data['data']['next_question']}")
                
                elif data["type"] == "error":
                    print(f"错误: {data['message']}")
                    break
            
            except websockets.exceptions.ConnectionClosed:
                break
        
        # 停止监听
        await websocket.send(json.dumps({"type": "stop"}))

# 运行测试
asyncio.run(test_realtime_speech())
```

### JavaScript客户端示例

```javascript
const conversationId = "your-conversation-id";
const ws = new WebSocket(`ws://localhost:8000/realtime-speech/${conversationId}/listen`);

ws.onopen = () => {
    console.log("WebSocket连接已建立");
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
        case "connected":
            console.log("已连接到实时语音服务");
            // 开始监听
            ws.send(JSON.stringify({type: "start"}));
            break;
            
        case "listening_started":
            console.log("已开始监听语音输入");
            break;
            
        case "transcription":
            console.log("转录结果:", data.text);
            break;
            
        case "assessment":
            console.log("评估结果:", data.data.assessment);
            console.log("下一题:", data.data.next_question);
            break;
            
        case "error":
            console.error("错误:", data.message);
            break;
    }
};

ws.onerror = (error) => {
    console.error("WebSocket错误:", error);
};

ws.onclose = () => {
    console.log("WebSocket连接已关闭");
};

// 停止监听
function stopListening() {
    ws.send(JSON.stringify({type: "stop"}));
}

// 关闭连接
function closeConnection() {
    ws.send(JSON.stringify({type: "close"}));
    ws.close();
}
```

## 📦 依赖安装

已更新 `requirements.txt`，新增依赖：

```bash
pyaudio==0.2.14      # 音频录制
webrtcvad==2.0.10    # 语音活动检测
numpy==1.26.3        # 数值计算
```

**注意**: `pyaudio` 在某些系统上可能需要额外的系统依赖：

**Ubuntu/Debian**:
```bash
sudo apt-get install portaudio19-dev python3-pyaudio
```

**macOS**:
```bash
brew install portaudio
```

**Windows**:
通常可以直接通过pip安装。

安装Python依赖：
```bash
pip install -r requirements.txt
```

## 🔄 工作流程

1. **客户端连接WebSocket**
   - 客户端连接到 `/realtime-speech/{conversation_id}/listen`
   - 服务端验证对话是否存在

2. **开始监听**
   - 客户端发送 `{"type": "start"}`
   - 服务端启动实时录音和VAD检测

3. **语音检测和转录**
   - VAD检测到语音活动
   - 当静音超过阈值时，自动保存语音段
   - 调用Whisper API进行转录
   - 发送转录结果给客户端

4. **评估和处理**
   - 将转录文本输入对话管理器
   - 执行评估和生成下一题
   - 发送评估结果给客户端

5. **停止监听**
   - 客户端发送 `{"type": "stop"}`
   - 服务端停止录音和VAD检测

## ⚙️ 配置参数

### RealtimeSpeechRecorder参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `sample_rate` | 16000 | 采样率（Hz） |
| `channels` | 1 | 声道数 |
| `chunk_size` | 1024 | 音频块大小 |
| `vad_mode` | 3 | VAD模式（0-3，越大越敏感） |
| `no_speech_threshold` | 1.0 | 无语音阈值（秒） |
| `vad_activation_rate` | 0.4 | VAD激活率阈值（0-1） |
| `vad_chunk_duration` | 0.5 | VAD检测时间窗口（秒） |

## 🐛 故障排除

### 1. PyAudio安装失败

**错误**: `pip install pyaudio` 失败

**解决方案**:
- Ubuntu/Debian: `sudo apt-get install portaudio19-dev`
- macOS: `brew install portaudio`
- Windows: 通常可以直接安装

### 2. 无法检测到麦克风

**错误**: 录音失败或没有音频输入

**解决方案**:
- 检查系统麦克风权限
- 确认麦克风设备正常工作
- 检查PyAudio是否能访问音频设备

### 3. VAD检测不准确

**问题**: 误检或漏检语音活动

**解决方案**:
- 调整 `vad_mode`（0-3）
- 调整 `vad_activation_rate`（0-1）
- 调整 `no_speech_threshold`（秒）

### 4. WebSocket连接失败

**错误**: 无法连接到WebSocket端点

**解决方案**:
- 确认服务已启动
- 检查端口是否正确（默认8000）
- 确认对话ID有效

## 📝 注意事项

1. **系统依赖**: `pyaudio` 需要系统级的音频库支持
2. **权限要求**: 需要麦克风访问权限
3. **性能考虑**: VAD检测和实时录音会消耗一定CPU资源
4. **网络延迟**: WebSocket通信受网络延迟影响
5. **并发限制**: 每个对话ID只能有一个活跃的WebSocket连接

## 🔗 相关文档

- [语音功能说明](./SPEECH_CAPABILITIES.md)
- [API文档](./API.md)
- [系统架构](./ARCHITECTURE.md)

## 📚 参考实现

本模块参考了以下实现：
- `/home/ubuntu/ASR-LLM-TTS/13_SenceVoice_QWen2.5_edgeTTS_realTime.py` - 实时语音交互
- `/home/ubuntu/user/user_voice_relay.ts` - WebSocket语音中继


