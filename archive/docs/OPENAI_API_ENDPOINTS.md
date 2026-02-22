# OpenAI API 接口地址说明

## 默认API地址

OpenAI的官方API基础地址：
```
https://api.openai.com/v1
```

## 主要API端点

### 1. Chat Completions（聊天完成）
**用途**：文本生成、对话

**端点**：
```
POST https://api.openai.com/v1/chat/completions
```

**在我们的系统中使用**：
- `services/llm.py` - `OpenAIService.chat_completion()`
- `services/llm.py` - `OpenAIService.chat_completion_json()`

**请求示例**：
```python
client.chat.completions.create(
    model="gpt-4-turbo",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### 2. Audio Transcriptions（语音转文本）
**用途**：Whisper API，语音转文本

**端点**：
```
POST https://api.openai.com/v1/audio/transcriptions
```

**在我们的系统中使用**：
- `services/speech.py` - `WhisperService.transcribe_audio()`

**请求示例**：
```python
client.audio.transcriptions.create(
    model="whisper-1",
    file=audio_file
)
```

### 3. Audio Speech（文本转语音）
**用途**：TTS API，文本转语音

**端点**：
```
POST https://api.openai.com/v1/audio/speech
```

**当前状态**：⚠️ 我们系统中未实现，但可以扩展

## 自定义API地址

### 使用代理或自定义端点

如果需要使用代理或自定义API地址，可以在创建OpenAI客户端时指定：

```python
from openai import OpenAI

# 使用自定义base_url
client = OpenAI(
    api_key="your-api-key",
    base_url="https://your-proxy.com/v1"  # 自定义地址
)
```

### 修改我们的代码

如果要使用自定义API地址，可以修改 `services/llm.py`：

```python
class OpenAIService(LLMService):
    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4", base_url: Optional[str] = None):
        self.client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )
        self.default_model = default_model
```

然后在`.env`文件中添加：
```bash
OPENAI_BASE_URL=https://your-custom-url.com/v1
```

## 常用API端点列表

| API功能 | 端点 | 方法 | 用途 |
|---------|------|------|------|
| Chat Completions | `/v1/chat/completions` | POST | 文本生成 |
| Audio Transcriptions | `/v1/audio/transcriptions` | POST | 语音转文本 |
| Audio Speech | `/v1/audio/speech` | POST | 文本转语音 |
| Models List | `/v1/models` | GET | 列出可用模型 |
| Model Retrieve | `/v1/models/{model}` | GET | 获取模型信息 |

## 检查当前使用的地址

运行以下命令查看当前配置：

```python
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 查看base_url
print(f"Base URL: {client.base_url}")
# 默认输出: https://api.openai.com/v1
```

## 网络要求

### 访问OpenAI API需要：

1. **网络连接**：能够访问 `api.openai.com`
2. **HTTPS**：所有请求使用HTTPS
3. **端口**：443（HTTPS默认端口）

### 如果无法访问

如果在中国大陆或其他地区无法直接访问，可以考虑：

1. **使用代理**：
   ```python
   import os
   os.environ['HTTP_PROXY'] = 'http://your-proxy:port'
   os.environ['HTTPS_PROXY'] = 'http://your-proxy:port'
   ```

2. **使用API代理服务**：
   - 配置自定义base_url指向代理服务

3. **使用VPN**：
   - 确保网络可以访问OpenAI API

## 测试API连接

```bash
# 使用curl测试
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY"

# 或使用我们的测试脚本
python test_api_key.py
```

## 总结

- **默认地址**：`https://api.openai.com/v1`
- **Chat API**：`https://api.openai.com/v1/chat/completions`
- **Whisper API**：`https://api.openai.com/v1/audio/transcriptions`
- **我们的代码**：使用OpenAI Python SDK，自动使用默认地址
- **自定义地址**：可以通过`base_url`参数配置





