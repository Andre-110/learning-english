# 语音能力说明

## 一、GPT-3.5-turbo的语音能力

### 直接回答：❌ 没有

**GPT-3.5-turbo本身是一个纯文本模型，没有内置的语音能力。**

它只能：
- ✅ 处理文本输入
- ✅ 生成文本输出
- ❌ 不能直接处理音频输入
- ❌ 不能直接生成音频输出

## 二、OpenAI的语音相关API

虽然GPT-3.5-turbo没有语音能力，但OpenAI提供了独立的语音API：

### 1. Whisper API（语音转文本，STT）

**功能**：将音频转换为文本

**模型**：`whisper-1`

**特点**：
- ✅ 支持多种音频格式（mp3, mp4, mpeg, mpga, m4a, wav, webm）
- ✅ 支持多语言识别
- ✅ 自动检测语言
- ✅ 高准确率

**在我们的系统中**：
- 代码位置：`services/speech.py` - `WhisperService`
- API端点：`POST /conversations/{id}/respond-audio`
- 用途：将用户语音输入转换为文本，然后进入正常的文本处理流程

### 2. TTS API（文本转语音）

**功能**：将文本转换为语音

**模型**：`tts-1` 或 `tts-1-hd`

**特点**：
- ✅ 多种语音选择
- ✅ 高质量语音合成
- ✅ 支持多种语言

**当前状态**：⚠️ 我们系统中未实现，但可以扩展

### 3. GPT-4o（多模态模型）

**GPT-4o是OpenAI的多模态模型，支持：**
- ✅ 文本输入/输出
- ✅ 图像输入
- ✅ 音频输入（语音）
- ✅ 音频输出（语音）

**注意**：GPT-4o是专门的模型，不是GPT-3.5-turbo的升级版

## 三、我们系统的语音实现

### 当前实现：语音转文本（STT）

```python
# services/speech.py
class WhisperService(SpeechService):
    def transcribe_audio(self, audio_file: BinaryIO) -> str:
        # 使用Whisper API转录音频
        transcript = self.client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=None  # 自动检测
        )
        return transcript.strip()
```

**工作流程**：
```
用户语音输入
    ↓
Whisper API转文本
    ↓
文本进入正常流程
    ↓
GPT-3.5-turbo/GPT-4处理
    ↓
返回文本响应
```

### 使用示例

```bash
# 发送语音文件
curl -X POST "http://localhost:8000/conversations/{id}/respond-audio" \
  -F "audio_file=@your_audio.mp3"
```

### 配置要求

```bash
# .env文件
OPENAI_API_KEY=sk-...  # 同一个API密钥用于Whisper和GPT
```

## 四、完整的语音对话流程

### 方案1：当前实现（语音输入 + 文本输出）

```
用户说话 → Whisper转文本 → GPT处理 → 文本回复
```

**优点**：
- ✅ 已实现
- ✅ 成本低（只需Whisper API费用）
- ✅ 响应快

**缺点**：
- ❌ 用户只能看到文本回复，不能听到语音

### 方案2：完整语音对话（语音输入 + 语音输出）

```
用户说话 → Whisper转文本 → GPT处理 → TTS转语音 → 语音回复
```

**需要添加**：
- TTS API集成
- 音频输出端点

**优点**：
- ✅ 完整的语音交互体验
- ✅ 更自然

**缺点**：
- ⚠️ 需要额外开发
- ⚠️ 成本增加（Whisper + TTS）

## 五、如何添加TTS功能

### 步骤1：创建TTS服务

```python
# services/tts.py
from openai import OpenAI
import io

class TTSService:
    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    
    def text_to_speech(
        self,
        text: str,
        voice: str = "alloy",  # alloy, echo, fable, onyx, nova, shimmer
        model: str = "tts-1"   # tts-1 或 tts-1-hd
    ) -> bytes:
        """将文本转换为语音"""
        response = self.client.audio.speech.create(
            model=model,
            voice=voice,
            input=text
        )
        return response.content
```

### 步骤2：添加语音输出API端点

```python
# api/tts_endpoint.py
@router.post("/conversations/{conversation_id}/respond-audio-full")
async def respond_with_audio_full(
    conversation_id: str,
    audio_file: UploadFile,
    tts_service: TTSService = Depends(get_tts_service)
):
    # 1. 语音转文本（Whisper）
    text = speech_service.transcribe_audio(audio_file)
    
    # 2. 处理回答（GPT）
    result = process_response(conversation_id, text)
    
    # 3. 文本转语音（TTS）
    audio_response = tts_service.text_to_speech(result['next_question'])
    
    # 4. 返回音频
    return Response(content=audio_response, media_type="audio/mpeg")
```

## 六、模型选择建议（语音场景）

### 语音输入场景

**推荐配置**：
```bash
# 使用GPT-3.5-turbo处理文本（成本低）
PRIMARY_LLM_MODEL=gpt-3.5-turbo

# Whisper用于语音转文本
# TTS用于文本转语音（如果实现）
```

**理由**：
- Whisper独立于GPT模型
- GPT-3.5-turbo足够处理文本对话
- 成本更低

### 如果需要语音理解能力

**GPT-4o**：
- ✅ 支持音频输入
- ✅ 支持音频输出
- ⚠️ 成本更高
- ⚠️ 需要特殊配置

## 七、成本对比

### 方案1：Whisper + GPT-3.5-turbo（当前）

| 服务 | 成本 |
|------|------|
| Whisper（语音转文本） | $0.006/分钟 |
| GPT-3.5-turbo（文本处理） | $0.0005/1K tokens |
| **总计（1分钟对话）** | **约$0.01** |

### 方案2：Whisper + GPT-3.5-turbo + TTS

| 服务 | 成本 |
|------|------|
| Whisper（语音转文本） | $0.006/分钟 |
| GPT-3.5-turbo（文本处理） | $0.0005/1K tokens |
| TTS（文本转语音） | $0.015/1K字符 |
| **总计（1分钟对话）** | **约$0.02-0.03** |

### 方案3：GPT-4o（多模态）

| 服务 | 成本 |
|------|------|
| GPT-4o（语音输入+输出） | $2.50/1M输入tokens, $10/1M输出tokens |
| **总计（1分钟对话）** | **约$0.05-0.10** |

## 八、总结

### GPT-3.5-turbo的语音能力

- ❌ **没有直接的语音能力**
- ✅ 但可以通过Whisper API实现语音输入
- ✅ 可以通过TTS API实现语音输出

### 我们系统的语音实现

- ✅ **已实现**：语音转文本（Whisper）
- ⚠️ **未实现**：文本转语音（TTS，可扩展）

### 推荐方案

**当前最佳实践**：
```
语音输入（Whisper） → 文本处理（GPT-3.5-turbo） → 文本输出
```

**成本低，性能好，已实现**

如果需要完整语音对话，可以添加TTS功能，或考虑使用GPT-4o。





