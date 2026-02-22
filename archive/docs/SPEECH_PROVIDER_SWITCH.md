# 语音服务提供商切换指南

## 📋 概述

系统现在支持两种语音识别方式：
1. **Whisper API**（云端）- OpenAI的Whisper API服务
2. **FunASR**（本地部署）- 阿里开源的FunASR/SenseVoice模型

## 🔄 切换方式

### 方式1: 环境变量配置（推荐）

在 `.env` 文件中配置：

```bash
# 选择语音服务提供商: "whisper" 或 "funasr"
SPEECH_PROVIDER=funasr

# FunASR配置（仅在SPEECH_PROVIDER=funasr时生效）
FUNASR_MODEL_DIR=/path/to/local/model  # 可选：本地模型目录
FUNASR_MODEL_NAME=iic/SenseVoiceSmall   # 模型名称（ModelScope）
FUNASR_LANGUAGE=auto                    # 语言: auto, zh, en, yue, ja, ko
```

### 方式2: 代码中指定

```python
from services.speech import SpeechServiceFactory

# 使用Whisper API
whisper_service = SpeechServiceFactory.create(provider="whisper")

# 使用FunASR本地部署
funasr_service = SpeechServiceFactory.create(
    provider="funasr",
    model_name="iic/SenseVoiceSmall",
    language="auto"
)
```

## 📦 FunASR部署步骤

### 1. 安装依赖

```bash
pip install funasr==1.1.12 modelscope==1.15.0
```

**注意**: FunASR需要PyTorch，如果还没有安装：

```bash
# CPU版本
pip install torch torchvision torchaudio

# GPU版本（CUDA 11.8）
pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu118
```

### 2. 下载模型（可选）

**方式A: 自动下载（推荐）**

模型会在首次使用时自动从ModelScope下载：

```python
service = FunASRService(model_name="iic/SenseVoiceSmall")
```

**方式B: 手动下载**

1. 访问 [ModelScope](https://www.modelscope.cn/models/iic/SenseVoiceSmall/files)
2. 下载模型文件到本地目录
3. 配置 `FUNASR_MODEL_DIR` 环境变量

### 3. 配置环境变量

在 `.env` 文件中：

```bash
SPEECH_PROVIDER=funasr
FUNASR_MODEL_NAME=iic/SenseVoiceSmall
FUNASR_LANGUAGE=auto
```

### 4. 测试部署

```bash
python test/test_funasr_deployment.py
```

## 🔍 两种方式对比

| 特性 | Whisper API | FunASR本地 |
|------|------------|-----------|
| **部署方式** | 云端API | 本地服务器 |
| **需要API key** | ✅ 是 | ❌ 否 |
| **网络依赖** | ✅ 需要 | ❌ 不需要 |
| **成本** | 按调用量计费 | 一次性部署 |
| **延迟** | 受网络影响 | 本地处理，延迟低 |
| **隐私性** | 数据发送到云端 | 数据本地处理 |
| **模型大小** | 无需存储 | ~500MB-2GB |
| **支持语言** | 多语言 | 中文、英文、粤语、日语、韩语 |
| **准确率** | 高 | 高（中文场景） |

## ⚙️ 配置参数说明

### Whisper API配置

```bash
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选：代理地址
```

### FunASR配置

```bash
SPEECH_PROVIDER=funasr
FUNASR_MODEL_DIR=/path/to/model          # 可选：本地模型目录
FUNASR_MODEL_NAME=iic/SenseVoiceSmall    # 模型名称
FUNASR_LANGUAGE=auto                      # 语言设置
```

**语言选项**:
- `auto`: 自动检测
- `zh`: 中文
- `en`: 英文
- `yue`: 粤语
- `ja`: 日语
- `ko`: 韩语
- `nospeech`: 无语音

## 🚀 使用示例

### 示例1: 使用Whisper API

```python
from services.speech import SpeechServiceFactory

# 默认使用Whisper API
service = SpeechServiceFactory.create(provider="whisper")

# 转录音频
with open("audio.wav", "rb") as f:
    text = service.transcribe_audio(f)
    print(text)
```

### 示例2: 使用FunASR本地部署

```python
from services.speech import SpeechServiceFactory

# 使用FunASR
service = SpeechServiceFactory.create(
    provider="funasr",
    model_name="iic/SenseVoiceSmall",
    language="auto"
)

# 转录音频
with open("audio.wav", "rb") as f:
    text = service.transcribe_audio(f)
    print(text)
```

### 示例3: 实时语音服务切换

```python
from services.realtime_speech import create_realtime_speech_service
from services.speech import SpeechServiceFactory
from config.settings import Settings

settings = Settings()

# 根据配置选择服务
if settings.speech_provider == "funasr":
    speech_service = SpeechServiceFactory.create(
        provider="funasr",
        model_name=settings.funasr_model_name
    )
else:
    speech_service = SpeechServiceFactory.create(provider="whisper")

# 创建实时语音服务
realtime_service = create_realtime_speech_service(speech_service=speech_service)
realtime_service.start_listening(on_transcription=lambda text: print(text))
```

## 🐛 故障排除

### FunASR相关问题

**1. 模型下载失败**

**错误**: `ConnectionError` 或下载超时

**解决方案**:
- 检查网络连接
- 使用国内镜像（ModelScope）
- 手动下载模型并配置 `FUNASR_MODEL_DIR`

**2. 模型加载失败**

**错误**: `FileNotFoundError` 或模型文件损坏

**解决方案**:
- 检查模型目录路径是否正确
- 重新下载模型
- 检查磁盘空间

**3. 内存不足**

**错误**: `OutOfMemoryError`

**解决方案**:
- 使用更小的模型（如SenseVoiceSmall）
- 减少batch size
- 使用GPU加速

**4. 依赖冲突**

**错误**: `ImportError` 或版本冲突

**解决方案**:
```bash
# 创建独立环境
conda create -n funasr python=3.10
conda activate funasr
pip install funasr==1.1.12
```

### Whisper API相关问题

参考 [WHISPER_API_ISSUE.md](./WHISPER_API_ISSUE.md)

## 📝 注意事项

1. **首次使用FunASR**: 模型会自动下载，可能需要几分钟到几十分钟
2. **模型存储**: FunASR模型会缓存在 `~/.cache/modelscope/` 目录
3. **性能**: FunASR首次加载模型较慢，后续调用会更快
4. **内存**: FunASR需要一定内存（建议至少4GB可用内存）
5. **切换**: 可以在运行时切换，但建议重启服务以确保配置生效

## 🔗 相关文档

- [实时语音集成](./REALTIME_SPEECH_INTEGRATION.md)
- [语音功能说明](./SPEECH_CAPABILITIES.md)
- [FunASR官方文档](https://github.com/alibaba-damo-academy/FunASR)


