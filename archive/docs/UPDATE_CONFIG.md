# 配置更新说明

## ✅ 配置已集中管理

现在所有LLM相关配置都使用全局变量 `llm_config` 统一管理。

## 如何修改配置

### 只需修改 .env 文件

```bash
# 编辑.env文件
nano .env

# 修改以下配置：
OPENAI_API_KEY=sk-你的新密钥
OPENAI_BASE_URL=https://yunwu.ai  # 或留空使用官方API
PRIMARY_LLM_MODEL=gpt-4-turbo
LLM_PROVIDER=openai
```

### 重启服务即可

```bash
pkill -f "uvicorn api.main"
source venv/bin/activate
uvicorn api.main:app --reload
```

**无需修改任何代码！**

## 配置管理架构

### 全局配置类

**文件**：`config/llm_config.py`

```python
class LLMConfig:
    """全局LLM配置"""
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
    PRIMARY_LLM_MODEL = os.getenv("PRIMARY_LLM_MODEL", "gpt-4-turbo")
    # ...
```

### 所有服务自动使用

- `services/llm.py` - 自动使用 `llm_config`
- `services/speech.py` - 自动使用 `llm_config`
- `api/main.py` - 自动使用 `llm_config`

## 优势

✅ **集中管理**：所有配置在一个地方
✅ **易于修改**：只需改.env文件
✅ **自动应用**：重启服务即可
✅ **无需改代码**：配置变更不涉及代码修改

## 当前配置

运行以下命令查看当前配置：

```bash
python -c "from config.llm_config import llm_config; \
print(f'API密钥: {llm_config.get_openai_api_key()[:10]}...'); \
print(f'Base URL: {llm_config.get_openai_base_url()}'); \
print(f'模型: {llm_config.get_primary_model()}')"
```

## 相关文档

- `docs/CONFIG_MANAGEMENT.md` - 详细配置管理说明

