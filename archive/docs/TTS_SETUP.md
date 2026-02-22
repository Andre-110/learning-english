# 文本转语音（TTS）配置指南

## 概述

系统已集成 **edge-tts**（Microsoft Edge TTS）作为文本转语音服务。

## ⚠️ 重要说明

**edge-tts 不是真正的本地部署！**

虽然 edge-tts 是一个可以本地安装的 Python 库，但它实际上是通过**网络请求**调用 Microsoft Edge 的**在线 TTS 服务**。这意味着：

- ❌ **需要网络连接**：必须能够访问互联网
- ❌ **不是离线运行**：无法在完全离线的环境中使用
- ❌ **依赖外部服务**：依赖 Microsoft Edge TTS 服务的可用性

**工作原理**：
```
本地 Python 代码 → 网络请求 → Microsoft Edge TTS 服务 → 返回音频数据
```

## 功能特性

- ✅ **免费使用**：无需 API 密钥
- ✅ **高质量语音**：Microsoft Edge 的神经网络语音合成
- ✅ **多语言支持**：支持多种语言和语音
- ✅ **可定制参数**：支持调整语速、音量、音调
- ⚠️ **需要网络**：必须能够访问 Microsoft Edge TTS 服务

## 安装

```bash
pip install edge-tts nest-asyncio
```

或使用 requirements.txt：

```bash
pip install -r requirements.txt
```

## API 端点

### 1. 文本转语音

**端点**: `POST /tts/text-to-speech`

**参数**:
- `text` (必需): 要转换的文本
- `voice` (可选): 语音名称（如 `en-US-JennyNeural`）
- `rate` (可选): 语速（如 `+0%`, `-50%`）
- `volume` (可选): 音量（如 `+0%`, `-50%`）
- `pitch` (可选): 音调（如 `+0Hz`, `-50Hz`）

**示例**:
```bash
curl -X POST "http://localhost:8000/tts/text-to-speech?text=Hello%20world&voice=en-US-JennyNeural" \
  --output audio.mp3
```

### 2. 列出可用语音

**端点**: `GET /tts/voices`

**参数**:
- `language` (可选): 语言代码（如 `en`, `zh`），None 表示所有语言

**示例**:
```bash
curl "http://localhost:8000/tts/voices?language=en"
```

## 使用示例

### Python 代码示例

```python
from services.tts import TTSServiceFactory

# 创建 TTS 服务
tts_service = TTSServiceFactory.create(provider="edge-tts")

# 生成语音
audio_data = tts_service.text_to_speech(
    text="Hello, this is a test.",
    voice="en-US-JennyNeural"
)

# 保存音频文件
with open("output.mp3", "wb") as f:
    f.write(audio_data)
```

### 列出可用语音

```python
from services.tts import TTSServiceFactory

tts_service = TTSServiceFactory.create(provider="edge-tts")

# 列出所有英语语音
voices = tts_service.list_voices(language="en")
for voice in voices[:10]:
    print(f"{voice['ShortName']} - {voice['Locale']} - {voice['Gender']}")
```

## 常用英语语音

- `en-US-JennyNeural` - 美式英语，女性
- `en-US-GuyNeural` - 美式英语，男性
- `en-GB-SoniaNeural` - 英式英语，女性
- `en-GB-RyanNeural` - 英式英语，男性
- `en-AU-NatashaNeural` - 澳式英语，女性

## 配置

可以在 `.env` 文件中配置默认语音：

```env
# TTS 配置（可选）
TTS_DEFAULT_VOICE=en-US-JennyNeural
```

## 注意事项

1. **⚠️ 网络要求**: edge-tts **必须**访问 Microsoft Edge TTS 服务，确保服务器可以访问互联网
   - edge-tts 不是真正的本地部署，它通过 HTTP 请求调用在线服务
   - 如果无法访问互联网，edge-tts 将无法工作
2. **异步处理**: TTS 服务使用异步处理，在 FastAPI 中会自动处理
3. **音频格式**: 默认输出 MP3 格式音频

## 真正的本地 TTS 方案

如果您需要**完全离线**的 TTS 方案，请参考 [TTS_LOCAL_OPTIONS.md](TTS_LOCAL_OPTIONS.md)：

- **pyttsx3** - 简单离线方案（使用系统 TTS）
- **ChatTTS** - 高质量离线方案（神经网络）
- **Coqui TTS** - 专业离线方案（可定制）

## 故障排除

### 问题：No audio was received

**可能原因**:
1. 网络连接问题（无法访问 Microsoft Edge TTS 服务）
2. 语音名称不正确
3. 文本内容为空或格式不正确

**解决方法**:
1. 检查网络连接
2. 使用 `/tts/voices` 端点验证可用的语音名称
3. 确保文本不为空且格式正确

### 问题：事件循环错误

如果遇到事件循环相关错误，确保已安装 `nest-asyncio`：

```bash
pip install nest-asyncio
```

## 集成到对话流程

TTS 服务可以集成到对话流程中，为系统问题生成语音版本：

```python
from services.tts import TTSServiceFactory

tts_service = TTSServiceFactory.create(provider="edge-tts")

# 在生成问题后，生成语音版本
next_question = "What do you like to do in your free time?"
audio_data = tts_service.text_to_speech(next_question)

# 返回给客户端
return {
    "question": next_question,
    "question_audio": audio_data  # base64 编码或文件路径
}
```

## 相关文件

- `services/tts.py` - TTS 服务实现
- `api/tts_endpoint.py` - TTS API 端点
- `test/test_tts.py` - TTS 测试脚本

