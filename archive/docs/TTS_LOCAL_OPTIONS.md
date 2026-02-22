# 真正的本地 TTS 方案

## 问题说明

edge-tts **不是真正的本地部署**，它需要网络连接来访问 Microsoft Edge 的在线 TTS 服务。

如果您需要**完全离线**的 TTS 方案，可以考虑以下选项：

## 方案1：pyttsx3（离线 TTS）

### 特点
- ✅ **完全离线**：不需要网络连接
- ✅ **跨平台**：支持 Windows、Linux、macOS
- ⚠️ **语音质量一般**：使用系统自带的 TTS 引擎
- ⚠️ **语音选择有限**：取决于系统安装的语音包

### 安装
```bash
pip install pyttsx3
```

### 使用示例
```python
import pyttsx3

engine = pyttsx3.init()
engine.say("Hello, world!")
engine.save_to_file("Hello, world!", "output.mp3")
engine.runAndWait()
```

## 方案2：ChatTTS（开源本地 TTS）

### 特点
- ✅ **完全离线**：本地运行，不需要网络
- ✅ **高质量语音**：神经网络语音合成
- ✅ **开源免费**
- ⚠️ **需要 GPU**：推荐使用 GPU 加速
- ⚠️ **安装复杂**：需要 PyTorch 等依赖

### 安装
```bash
pip install ChatTTS
```

### 使用示例
```python
import ChatTTS

chat = ChatTTS.Chat()
chat.load_models()

texts = ["Hello, world!"]
wavs = chat.infer(texts)
```

## 方案3：Coqui TTS（开源本地 TTS）

### 特点
- ✅ **完全离线**：本地运行
- ✅ **高质量语音**：多种预训练模型
- ✅ **可定制**：可以训练自己的模型
- ⚠️ **资源消耗大**：需要较多内存和计算资源

### 安装
```bash
pip install TTS
```

### 使用示例
```python
from TTS.api import TTS

tts = TTS("tts_models/en/ljspeech/tacotron2-DDC")
tts.tts_to_file("Hello, world!", file_path="output.wav")
```

## 方案4：gTTS（Google TTS，需要网络）

### 特点
- ✅ **简单易用**
- ✅ **高质量语音**
- ❌ **需要网络**：调用 Google TTS 服务
- ❌ **有使用限制**：可能有请求频率限制

### 安装
```bash
pip install gtts
```

### 使用示例
```python
from gtts import gTTS

tts = gTTS("Hello, world!", lang="en")
tts.save("output.mp3")
```

## 推荐方案对比

| 方案 | 离线 | 质量 | 易用性 | 资源消耗 | 推荐场景 |
|------|------|------|--------|----------|----------|
| **pyttsx3** | ✅ | ⭐⭐ | ⭐⭐⭐⭐⭐ | 低 | 简单离线需求 |
| **ChatTTS** | ✅ | ⭐⭐⭐⭐ | ⭐⭐⭐ | 中-高 | 高质量离线需求 |
| **Coqui TTS** | ✅ | ⭐⭐⭐⭐⭐ | ⭐⭐ | 高 | 专业离线需求 |
| **edge-tts** | ❌ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 低 | 有网络环境 |
| **gTTS** | ❌ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 低 | 有网络环境 |

## 集成到系统

如果需要集成真正的本地 TTS，可以：

1. **创建新的 TTS 服务类**（参考 `services/tts.py`）
2. **实现 `TTSService` 接口**
3. **更新 `TTSServiceFactory`** 以支持新的提供商

示例结构：
```python
class LocalTTSService(TTSService):
    """本地 TTS 服务"""
    
    def text_to_speech(self, text: str, ...) -> bytes:
        # 本地生成音频，不需要网络
        pass
```

## 建议

- **如果有网络**：使用 edge-tts 或 gTTS（简单、高质量）
- **如果需要离线**：使用 pyttsx3（简单）或 ChatTTS（高质量）
- **如果需要专业级**：使用 Coqui TTS（可定制、高质量）

