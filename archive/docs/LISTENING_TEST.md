# 听力测试说明

## 📋 概述

系统支持**语音输入**功能，使用OpenAI Whisper API将用户的语音转换为文本，然后进入正常的评估流程。

## 🎯 功能说明

### 当前实现

- ✅ **语音转文本（STT）**: 使用Whisper API
- ✅ **语音输入API**: `POST /conversations/{id}/respond-audio`
- ✅ **支持格式**: mp3, wav, m4a, mp4, webm等
- ⚠️ **文本转语音（TTS）**: 未实现（可扩展）

### 工作流程

```
用户语音输入（音频文件）
    ↓
Whisper API转文本
    ↓
文本标准化处理（中英文混合）
    ↓
进入正常评估流程
    ↓
返回评估结果和下一题（文本）
```

## 🧪 测试方法

### 方法1: 使用测试脚本

```bash
# 测试API端点（需要服务运行）
python test/test_listening.py

# 只测试Whisper服务（不依赖API）
python test/test_listening.py --service-only
```

### 方法2: 使用curl命令

```bash
# 1. 开始对话
CONV_ID=$(curl -s -X POST "http://localhost:8000/conversations/start" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['conversation_id'])")

# 2. 发送语音文件
curl -X POST "http://localhost:8000/conversations/$CONV_ID/respond-audio" \
  -F "audio_file=@your_audio.mp3"
```

### 方法3: 使用Python requests

```python
import requests

# 开始对话
resp = requests.post(
    "http://localhost:8000/conversations/start",
    json={"user_id": "test_user"}
)
conv_id = resp.json()["conversation_id"]

# 发送语音文件
with open("your_audio.mp3", "rb") as f:
    files = {"audio_file": ("audio.mp3", f, "audio/mpeg")}
    resp = requests.post(
        f"http://localhost:8000/conversations/{conv_id}/respond-audio",
        files=files
    )
    
result = resp.json()
print(f"转录文本: {result['transcribed_text']}")
print(f"评估分数: {result['assessment']['ability_profile']['overall_score']}")
```

## 📝 测试音频要求

### 格式要求

- **支持格式**: mp3, wav, m4a, mp4, webm, mpeg, mpga
- **推荐格式**: mp3或wav（兼容性最好）

### 内容要求

- **语言**: 英语或中英文混合
- **时长**: 建议5-30秒
- **内容**: 回答问题的语音（如："I am a student. I like reading books."）

### 准备测试音频

#### 方法1: 使用文本转语音工具

```bash
# 使用gTTS（Google Text-to-Speech）
pip install gtts
python -c "
from gtts import gTTS
tts = gTTS('I am a student. I like reading books very much.', lang='en')
tts.save('test_audio.mp3')
"
```

#### 方法2: 使用系统录音

```bash
# Linux: 使用arecord
arecord -d 5 -f cd test_audio.wav

# macOS: 使用say命令
say "I am a student. I like reading books." -o test_audio.aiff
```

#### 方法3: 在线工具

- 使用在线TTS工具生成音频
- 或使用手机录音功能

## 🔍 API端点详情

### POST /conversations/{conversation_id}/respond-audio

**功能**: 通过语音输入回答问题

**请求**:
- **方法**: POST
- **Content-Type**: multipart/form-data
- **参数**:
  - `audio_file`: 音频文件（必需）

**响应**:
```json
{
  "transcribed_text": "I am a student. I like reading books.",
  "normalized_text": "I am a student. I like reading books.",
  "language_analysis": {
    "primary_language": "en",
    "is_mixed": false
  },
  "next_question": "What do you usually do on weekends?",
  "assessment": {
    "ability_profile": {
      "overall_score": 75.0,
      "cefr_level": "B1",
      "strengths": ["词汇丰富"],
      "weaknesses": ["复杂句式"]
    }
  },
  "user_profile": {...},
  "round_number": 1
}
```

## ⚙️ 配置要求

### 环境变量

```bash
# .env文件
OPENAI_API_KEY=sk-...  # 用于Whisper API
OPENAI_BASE_URL=https://yunwu.ai  # 可选，代理地址
```

### 服务启动

确保语音端点已注册（默认已注册）：

```python
# api/main.py
if SPEECH_ENABLED:
    app.include_router(speech_router)
```

## 🐛 常见问题

### 1. 音频格式不支持

**错误**: `不支持的音频格式: audio/xxx`

**解决**: 使用支持的格式（mp3, wav, m4a等）

### 2. 转录失败

**错误**: `音频转录失败，无法识别语音内容`

**可能原因**:
- 音频文件损坏
- 音频内容太短或无声
- API配额不足

**解决**: 检查音频文件，确保有清晰的语音内容

### 3. API调用超时

**错误**: `Read timed out`

**解决**: 增加超时时间，或检查网络连接

## 📊 测试结果示例

```
=== 听力测试 - 语音转文本功能 ===

1. 开始对话...
   ✅ 对话已开始: abc123-def456-...

2. 测试语音转文本...
   ----------------------------------------------------------------------
   测试文件: test_audio.mp3
   ✅ 转录成功
      原始转录: I am a student. I like reading books very much.
      标准化文本: I am a student. I like reading books very much.
      语言分析:
        - 主要语言: en
        - 是否混合: False
      评估结果:
        - 分数: 75.0/100
        - CEFR等级: B1
      下一题: What do you usually do on weekends?...

✅ 听力测试完成！
```

## 🚀 扩展功能

### 添加文本转语音（TTS）

如果需要完整的语音对话，可以添加TTS功能：

1. 创建TTS服务（`services/tts.py`）
2. 添加语音输出端点
3. 返回音频响应

详见 `docs/SPEECH_CAPABILITIES.md`

## 📚 相关文档

- `docs/SPEECH_CAPABILITIES.md` - 语音能力详细说明
- `services/speech.py` - 语音服务实现
- `api/speech_endpoint.py` - 语音API端点
- `test/test_listening.py` - 测试脚本





