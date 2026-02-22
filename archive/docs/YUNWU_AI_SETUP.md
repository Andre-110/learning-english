# yunwu.ai API代理配置

## ✅ 配置成功

已成功配置使用 yunwu.ai 作为 OpenAI API 代理服务。

## 配置信息

### .env文件配置

```bash
OPENAI_API_KEY=sk-你的密钥
OPENAI_BASE_URL=https://yunwu.ai
PRIMARY_LLM_MODEL=gpt-4-turbo
```

### API地址

- **代理地址**：`https://yunwu.ai/v1`
- **Chat API**：`https://yunwu.ai/v1/chat/completions`
- **Whisper API**：`https://yunwu.ai/v1/audio/transcriptions`

## 代码修改

### 1. LLM服务支持自定义base_url

**文件**：`services/llm.py`

```python
class OpenAIService(LLMService):
    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4", base_url: Optional[str] = None):
        base_url = base_url or os.getenv("OPENAI_BASE_URL")
        if base_url:
            if not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = OpenAI(api_key=api_key)
```

### 2. 语音服务支持自定义base_url

**文件**：`services/speech.py`

```python
class WhisperService(SpeechService):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        base_url = base_url or os.getenv("OPENAI_BASE_URL")
        if base_url:
            if not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"
            self.client = OpenAI(api_key=api_key, base_url=base_url)
```

## 测试结果

### ✅ 测试通过

```
测试1: GPT-4-turbo 文本生成（通过yunwu.ai代理）
✅ GPT-4-turbo 调用成功
   响应: Hello

测试2: JSON格式输出
✅ JSON格式输出成功
   响应: {"test": "success"}
```

## 使用说明

### 1. 配置.env文件

```bash
OPENAI_API_KEY=你的API密钥
OPENAI_BASE_URL=https://yunwu.ai
```

### 2. 重启服务

```bash
pkill -f "uvicorn api.main"
source venv/bin/activate
uvicorn api.main:app --reload
```

### 3. 测试

```bash
# 测试代理连接
python test_yunwu_api.py

# 测试完整流程
python test_quick.py
```

## 优势

使用 yunwu.ai 代理的优势：

1. **网络访问**：可能解决某些地区的网络访问问题
2. **稳定性**：代理服务可能提供更好的稳定性
3. **成本**：某些代理服务可能提供更优惠的价格

## 切换回官方API

如果需要切换回OpenAI官方API：

```bash
# 方法1：删除OPENAI_BASE_URL配置
# 编辑.env文件，删除或注释掉OPENAI_BASE_URL行

# 方法2：设置为空
OPENAI_BASE_URL=

# 方法3：设置为官方地址
OPENAI_BASE_URL=https://api.openai.com
```

## 注意事项

1. **API密钥格式**：确保API密钥格式正确
2. **base_url格式**：代码会自动添加`/v1`后缀
3. **代理兼容性**：确保代理服务兼容OpenAI API格式

## 故障排查

### 问题1：代理连接失败

```bash
# 检查网络连接
curl https://yunwu.ai

# 检查配置
cat .env | grep OPENAI_BASE_URL
```

### 问题2：API调用失败

```bash
# 运行测试脚本
python test_yunwu_api.py

# 查看详细错误信息
```

## 相关文件

- `services/llm.py` - LLM服务（支持自定义base_url）
- `services/speech.py` - 语音服务（支持自定义base_url）
- `test_yunwu_api.py` - yunwu.ai代理测试脚本
- `.env` - 环境变量配置





