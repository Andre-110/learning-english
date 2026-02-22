# 配置管理说明

## 全局配置管理

现在所有LLM相关配置都集中在 `config/llm_config.py` 中管理，使用全局变量 `llm_config`。

## 配置位置

### 统一配置源

**文件**：`config/llm_config.py`

```python
class LLMConfig:
    """LLM配置类 - 全局单例配置"""
    
    # OpenAI配置
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL")
    PRIMARY_LLM_MODEL: str = os.getenv("PRIMARY_LLM_MODEL", "gpt-4-turbo")
    SECONDARY_LLM_MODEL: str = os.getenv("SECONDARY_LLM_MODEL", "gpt-3.5-turbo")
    
    # Anthropic配置
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    
    # LLM提供商
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower()
```

## 使用方法

### 1. 修改配置（只需改.env文件）

```bash
# 编辑.env文件
nano .env

# 修改以下配置即可：
OPENAI_API_KEY=sk-你的新密钥
OPENAI_BASE_URL=https://yunwu.ai  # 或留空使用官方API
PRIMARY_LLM_MODEL=gpt-4-turbo
LLM_PROVIDER=openai
```

### 2. 代码中自动使用全局配置

所有服务类都会自动从 `llm_config` 读取配置：

```python
# services/llm.py
from config.llm_config import llm_config

class OpenAIService(LLMService):
    def __init__(self, api_key=None, default_model=None, base_url=None):
        # 自动使用全局配置
        api_key = api_key or llm_config.get_openai_api_key()
        base_url = base_url or llm_config.get_openai_base_url()
        default_model = default_model or llm_config.get_primary_model()
```

### 3. 运行时重新加载配置

如果需要运行时更新配置：

```python
from config.llm_config import llm_config

# 重新加载.env文件
llm_config.reload()
```

## 配置优先级

1. **函数参数**（最高优先级）
   ```python
   OpenAIService(api_key="custom_key")  # 使用custom_key
   ```

2. **全局配置**（默认）
   ```python
   OpenAIService()  # 使用llm_config中的配置
   ```

3. **环境变量**（通过llm_config读取）

## 修改配置的步骤

### 步骤1：修改.env文件

```bash
# 只需修改.env文件
OPENAI_API_KEY=sk-新密钥
OPENAI_BASE_URL=https://yunwu.ai
PRIMARY_LLM_MODEL=gpt-4-turbo
```

### 步骤2：重启服务

```bash
pkill -f "uvicorn api.main"
source venv/bin/activate
uvicorn api.main:app --reload
```

**无需修改任何代码！**

## 配置项说明

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| API密钥 | `OPENAI_API_KEY` | None | OpenAI API密钥 |
| API地址 | `OPENAI_BASE_URL` | None | 代理地址（如https://yunwu.ai） |
| 主要模型 | `PRIMARY_LLM_MODEL` | gpt-4-turbo | 用于评估和生成 |
| 辅助模型 | `SECONDARY_LLM_MODEL` | gpt-3.5-turbo | 用于摘要等 |
| 提供商 | `LLM_PROVIDER` | openai | openai或anthropic |

## 优势

### ✅ 集中管理
- 所有配置在一个地方
- 易于维护和修改

### ✅ 自动应用
- 修改.env后重启服务即可
- 无需修改代码

### ✅ 灵活覆盖
- 支持函数参数覆盖
- 支持运行时重新加载

### ✅ 类型安全
- 使用配置类管理
- 提供类型提示

## 示例

### 切换API密钥

```bash
# 1. 修改.env
OPENAI_API_KEY=sk-新密钥

# 2. 重启服务
pkill -f uvicorn
uvicorn api.main:app --reload
```

### 切换API地址

```bash
# 1. 修改.env
OPENAI_BASE_URL=https://yunwu.ai  # 使用代理
# 或
# OPENAI_BASE_URL=  # 使用官方API

# 2. 重启服务
```

### 切换模型

```bash
# 1. 修改.env
PRIMARY_LLM_MODEL=gpt-4
# 或
PRIMARY_LLM_MODEL=gpt-3.5-turbo

# 2. 重启服务
```

## 相关文件

- `config/llm_config.py` - LLM配置管理（核心）
- `services/llm.py` - LLM服务（使用llm_config）
- `services/speech.py` - 语音服务（使用llm_config）
- `api/main.py` - API主文件（使用llm_config）
- `.env` - 环境变量配置文件

## 总结

✅ **配置集中管理**：所有LLM配置在 `config/llm_config.py`
✅ **只需修改.env**：修改配置无需改代码
✅ **自动应用**：重启服务即可生效
✅ **灵活覆盖**：支持参数覆盖和运行时重载

现在修改配置只需要编辑 `.env` 文件即可！





