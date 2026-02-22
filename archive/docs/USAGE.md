# 使用指南

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填入配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：
```env
OPENAI_API_KEY=your_api_key_here
PRIMARY_LLM_MODEL=gpt-4
LLM_PROVIDER=openai
```

### 3. 启动服务

```bash
uvicorn api.main:app --reload
```

服务将在 `http://localhost:8000` 启动。

## API使用示例

### 1. 开始对话

```bash
curl -X POST "http://localhost:8000/conversations/start" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123"
  }'
```

响应：
```json
{
  "conversation_id": "uuid-here",
  "initial_question": "Can you tell me about yourself?",
  "message": "对话已开始"
}
```

### 2. 回答问题

```bash
curl -X POST "http://localhost:8000/conversations/{conversation_id}/respond" \
  -H "Content-Type: application/json" \
  -d '{
    "user_response": "I am a student. I like reading books."
  }'
```

响应：
```json
{
  "next_question": "What kind of books do you like?",
  "assessment": {
    "round_number": 1,
    "dimension_scores": [...],
    "ability_profile": {
      "overall_score": 65.0,
      "cefr_level": "A2",
      "strengths": ["基本表达"],
      "weaknesses": ["语法准确性"]
    }
  },
  "user_profile": {...},
  "round_number": 1
}
```

### 3. 获取对话信息

```bash
curl "http://localhost:8000/conversations/{conversation_id}"
```

### 4. 结束对话

```bash
curl -X POST "http://localhost:8000/conversations/{conversation_id}/end"
```

## Python客户端示例

```python
import requests

BASE_URL = "http://localhost:8000"

# 开始对话
response = requests.post(
    f"{BASE_URL}/conversations/start",
    json={"user_id": "user123"}
)
data = response.json()
conversation_id = data["conversation_id"]
print(f"初始问题: {data['initial_question']}")

# 回答
user_answer = input("你的回答: ")
response = requests.post(
    f"{BASE_URL}/conversations/{conversation_id}/respond",
    json={"user_response": user_answer}
)
data = response.json()
print(f"下一题: {data['next_question']}")
print(f"评估分数: {data['assessment']['ability_profile']['overall_score']}")
print(f"CEFR等级: {data['assessment']['ability_profile']['cefr_level']}")
```

## 系统特性

### 1. 动态自适应
- 系统根据用户表现自动调整题目难度
- 能力画像实时更新

### 2. 多维度评估
- 内容相关性
- 语言准确性
- 表达流利度
- 交互深度

### 3. 上下文管理
- 自动摘要长对话
- 保持上下文连贯性

### 4. 可扩展性
- 支持多种LLM提供商
- 可切换存储后端
- 模块化设计，易于扩展

## 配置说明

### LLM提供商
- `openai`: 使用OpenAI API
- `anthropic`: 使用Anthropic API

### 存储后端
- `memory`: 内存存储（开发测试用）
- `database`: 数据库存储（待实现）
- `redis`: Redis存储（待实现）

### 模型选择
- `PRIMARY_LLM_MODEL`: 主要模型（用于评估和生成）
- `SECONDARY_LLM_MODEL`: 辅助模型（用于摘要等）

## 故障排查

### 1. API密钥错误
确保 `.env` 文件中的API密钥正确。

### 2. 模型不可用
检查模型名称是否正确，确保账户有权限使用该模型。

### 3. 上下文过长
系统会自动生成摘要，如果仍出现问题，可以调整 `CONTEXT_SUMMARY_INTERVAL` 配置。

## 开发建议

1. **提示词优化**：修改 `prompts/templates.py` 中的提示词模板
2. **评估标准**：调整评估维度和评分标准
3. **主题扩展**：在 `config/topics.py` 中添加更多主题
4. **存储扩展**：实现数据库或Redis存储后端


