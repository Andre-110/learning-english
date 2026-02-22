# Whisper模型说明

## 使用的模型

系统使用 **`whisper-1`** 模型进行语音转文本。

## 模型信息

- **模型名称**: `whisper-1`
- **提供商**: OpenAI
- **API端点**: `/v1/audio/transcriptions`
- **功能**: 语音转文本（Speech-to-Text, STT）

## 代码位置

### 服务实现
```python
# services/speech.py
transcript = self.client.audio.transcriptions.create(
    model="whisper-1",  # 使用whisper-1模型
    file=audio_file,
    language=language,
    response_format="text"
)
```

### API端点
```python
# api/speech_endpoint.py
@router.post("/{conversation_id}/respond-audio")
async def respond_with_audio(...):
    # 调用Whisper服务转录音频
    transcribed_text = speech_service.transcribe_audio(audio_io)
```

## 支持的音频格式

- mp3
- mp4
- mpeg
- mpga
- m4a
- wav
- webm

## API要求

### 官方OpenAI API

- **端点**: `https://api.openai.com/v1/audio/transcriptions`
- **认证**: 需要有效的OpenAI API密钥
- **费用**: $0.006/分钟

### 代理服务

⚠️ **注意**: 不是所有代理服务都支持Whisper API

- ✅ 支持: 需要代理服务实现Audio API端点
- ❌ 不支持: yunwu.ai等只支持Chat API的代理

## 当前配置

系统配置为：
- **模型**: `whisper-1` ✅
- **API端点**: 默认使用官方OpenAI API
- **代理支持**: 可通过`WHISPER_BASE_URL`环境变量指定

## 使用示例

```python
from services.speech import SpeechServiceFactory

# 创建Whisper服务
speech_service = SpeechServiceFactory.create(provider="whisper")

# 转录音频
with open("audio.mp3", "rb") as f:
    audio_io = io.BytesIO(f.read())
    text = speech_service.transcribe_audio(audio_io)
    print(text)
```

## 相关文档

- `docs/WHISPER_API_ISSUE.md` - Whisper API问题说明
- `docs/LISTENING_TEST.md` - 听力测试说明
- `services/speech.py` - Whisper服务实现





