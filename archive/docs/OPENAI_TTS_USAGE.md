# OpenAI TTS API 使用指南（通过 yunwu.ai）

## ✅ 已成功集成

OpenAI TTS API 已成功集成到系统中，通过 yunwu.ai 代理调用。

## 配置

### 环境变量

在 `.env` 文件中配置：

```env
# OpenAI API 配置（用于 TTS）
OPENAI_API_KEY=sk-xxxxx
OPENAI_BASE_URL=https://yunwu.ai

# TTS 配置
TTS_PROVIDER=openai
TTS_MODEL=gpt-4o-mini-tts
TTS_DEFAULT_VOICE=alloy
```

## API 端点

### 1. 列出可用语音

**端点**: `GET /tts/voices`

**示例**:
```bash
curl "http://localhost:8000/tts/voices"
```

**响应**:
```json
{
  "total": 6,
  "voices": [
    {
      "name": "alloy",
      "locale": "en-US",
      "gender": "Neutral",
      "friendly_name": "OpenAI Alloy"
    },
    ...
  ]
}
```

### 2. 文本转语音

**端点**: `POST /tts/text-to-speech`

**参数**:
- `text` (必需): 要转换的文本
- `voice` (可选): 语音名称（alloy, echo, fable, onyx, nova, shimmer）
- `rate`, `volume`, `pitch` (可选): OpenAI TTS 不支持这些参数，会被忽略

**示例**:
```bash
curl -X POST "http://localhost:8000/tts/text-to-speech?text=Hello%20world&voice=alloy" \
  --output audio.mp3
```

**Python 示例**:
```python
import requests

response = requests.post(
    "http://localhost:8000/tts/text-to-speech",
    params={
        "text": "Hello, world!",
        "voice": "alloy"
    }
)

if response.status_code == 200:
    with open("output.mp3", "wb") as f:
        f.write(response.content)
    print("音频已保存")
```

## 支持的语音

OpenAI TTS 支持 6 种语音：

| 语音名称 | 性别 | 特点 |
|---------|------|------|
| **alloy** | 中性 | 平衡、通用 |
| **echo** | 男性 | 深沉、专业 |
| **fable** | 男性 | 英国口音 |
| **onyx** | 男性 | 深沉、有力 |
| **nova** | 女性 | 年轻、活泼 |
| **shimmer** | 女性 | 温暖、友好 |

## 使用示例

### Python 代码示例

```python
from services.tts import TTSServiceFactory

# 创建 OpenAI TTS 服务
tts_service = TTSServiceFactory.create(
    provider="openai",
    model="gpt-4o-mini-tts",
    default_voice="alloy"
)

# 生成语音
audio_data = tts_service.text_to_speech(
    text="Hello, this is a test.",
    voice="nova"
)

# 保存文件
with open("output.mp3", "wb") as f:
    f.write(audio_data)
```

### 异步使用

```python
import asyncio
from services.tts import TTSServiceFactory

async def main():
    tts_service = TTSServiceFactory.create(
        provider="openai",
        model="gpt-4o-mini-tts"
    )
    
    audio_data = await tts_service._text_to_speech_async(
        text="Hello, world!",
        voice="alloy"
    )
    
    with open("output.mp3", "wb") as f:
        f.write(audio_data)

asyncio.run(main())
```

## 测试

运行测试脚本：

```bash
# 测试 OpenAI TTS 服务
python3 test/test_openai_tts.py

# 测试 API 端点
python3 test/test_tts_api.py
```

## 注意事项

1. **模型名称**: yunwu.ai 使用 `gpt-4o-mini-tts` 作为模型名称
2. **参数限制**: OpenAI TTS 不支持 `rate`、`volume`、`pitch` 参数
3. **网络要求**: 需要能够访问 yunwu.ai API
4. **API 密钥**: 确保 API 密钥有 TTS 访问权限

## 故障排除

### 问题：403 错误 - 无权限访问模型

**解决方案**:
- 检查 API 密钥是否有 TTS 访问权限
- 确认模型名称是 `gpt-4o-mini-tts`
- 检查 yunwu.ai 账户配置

### 问题：网络连接失败

**解决方案**:
- 检查服务器网络连接
- 确认可以访问 `yunwu.ai`
- 检查防火墙设置

## 与 edge-tts 对比

| 特性 | OpenAI TTS | edge-tts |
|------|-----------|----------|
| **提供商** | OpenAI (yunwu.ai) | Microsoft Edge |
| **模型** | gpt-4o-mini-tts | 多种语音 |
| **语音数量** | 6 种 | 500+ 种 |
| **质量** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **网络要求** | ✅ 需要 | ✅ 需要 |
| **费用** | 按使用量 | 免费 |
| **参数支持** | 仅 voice | voice, rate, volume, pitch |

## 相关文件

- `services/tts.py` - TTS 服务实现
- `api/tts_endpoint.py` - API 端点
- `test/test_openai_tts.py` - 测试脚本
- `config/settings.py` - 配置管理

