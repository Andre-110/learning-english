# Whisper API问题说明

## 问题现象

测试语音转文本功能时出现错误：
```
Error code: 429 - multipart: NextPart: EOF
invalid_audio_request
```

## 问题原因

**yunwu.ai代理服务可能不支持Whisper API**

测试发现：
- 使用yunwu.ai作为base_url时，Whisper API返回HTML页面（代理的前端页面）
- 说明yunwu.ai代理可能只支持Chat Completions API，不支持Audio API

## 解决方案

### 方案1: 使用官方OpenAI API（推荐）

修改`.env`文件，删除或注释`OPENAI_BASE_URL`：

```bash
# .env
OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=  # 注释掉，使用官方API
```

**优点**:
- ✅ Whisper API完全支持
- ✅ 功能完整

**缺点**:
- ⚠️ 可能需要VPN（如果在中国大陆）
- ⚠️ 成本可能较高

### 方案2: 使用支持Whisper的代理服务

寻找支持Audio API的代理服务，或使用支持Whisper的代理。

### 方案3: 分离配置（推荐用于生产）

为Whisper API单独配置：

```python
# services/speech.py
def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
    api_key = api_key or llm_config.get_openai_api_key()
    
    # Whisper API使用官方端点（某些代理不支持）
    whisper_base_url = os.getenv("WHISPER_BASE_URL")  # 可选：Whisper专用代理
    if not whisper_base_url:
        # 默认使用官方API
        self.client = OpenAI(api_key=api_key)
    else:
        self.client = OpenAI(api_key=api_key, base_url=whisper_base_url)
```

## 当前状态

- ✅ 代码已实现Whisper API集成
- ✅ 错误处理已改进
- ⚠️ yunwu.ai代理不支持Whisper API
- ✅ 可以使用官方OpenAI API

## 测试建议

1. **使用官方API测试**:
   ```bash
   # 临时修改.env，删除OPENAI_BASE_URL
   # 然后运行测试
   python test/test_listening.py
   ```

2. **检查代理支持**:
   - 联系yunwu.ai确认是否支持Whisper API
   - 或寻找其他支持Audio API的代理服务

## 相关文件

- `services/speech.py` - Whisper服务实现
- `api/speech_endpoint.py` - 语音API端点
- `test/test_listening.py` - 测试脚本





