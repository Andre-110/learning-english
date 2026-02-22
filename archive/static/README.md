# LinguaCoach 流式语音对话前端

这是一个现代化的Web前端界面，支持流式语音输入和输出，用于英语口语对话测评系统。

## 功能特性

- ✅ **流式语音输入**：实时录音并发送到服务器
- ✅ **流式语音输出**：实时接收并播放TTS音频
- ✅ **对话历史显示**：实时显示对话内容
- ✅ **评估结果展示**：显示用户能力评估和画像
- ✅ **现代化UI**：美观、响应式的用户界面

## 使用方法

1. **启动后端服务**：
   ```bash
   cd /home/ubuntu/learning_english
   python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```

2. **访问前端界面**：
   打开浏览器访问：`http://localhost:8000/`

3. **开始对话**：
   - 输入用户ID（例如：`user_001`）
   - 点击"开始对话"按钮
   - 等待初始问题出现

4. **语音对话**：
   - 点击"开始录音"按钮
   - 对着麦克风说话
   - 点击"停止录音"按钮
   - 系统会自动识别语音、处理对话并播放回复

## 技术栈

- **前端**：HTML5, CSS3, JavaScript (ES6+)
- **音频录制**：Web Audio API, MediaRecorder API
- **实时通信**：WebSocket
- **后端**：FastAPI, WebSocket

## 浏览器兼容性

- Chrome/Edge (推荐)
- Firefox
- Safari (部分功能可能受限)

## 注意事项

1. **麦克风权限**：首次使用时需要授予浏览器麦克风访问权限
2. **HTTPS要求**：某些浏览器在HTTPS环境下才能访问麦克风
3. **音频格式**：浏览器会自动选择支持的音频格式（通常是WebM）

## 文件结构

```
static/
├── index.html      # 主HTML文件
├── styles.css      # 样式文件
├── app.js          # JavaScript逻辑
└── README.md       # 本文件
```

## API端点

- `GET /` - 前端页面
- `GET /static/*` - 静态资源
- `POST /conversations/start` - 开始对话
- `WebSocket /streaming-voice/{conversation_id}/chat` - 流式语音对话

## 开发说明

前端代码使用原生JavaScript编写，没有依赖外部库，便于维护和部署。







