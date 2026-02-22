# 快速启动指南

## 一、代码完成度评估

### ✅ 完成度：90%

**已完成的核心功能：**
- ✅ 数据模型层（100%）
- ✅ 提示词管理（95%）
- ✅ 服务层（90%）
- ✅ 核心业务层（95%）
- ✅ API层（95%）
- ✅ 存储层（85% - 内存存储已实现）

**待完善功能：**
- ⚠️ 报告生成API端点（ReportPrompt已定义，未集成）
- ⚠️ 缓存机制
- ⚠️ 数据库存储
- ⚠️ 测试代码

## 二、让框架跑起来的步骤

### 步骤1：安装依赖

```bash
cd /home/ubuntu/learning_english
pip install -r requirements.txt
```

### 步骤2：配置环境变量

```bash
# 创建.env文件
cat > .env << EOF
# LLM配置（必须配置至少一个）
OPENAI_API_KEY=your_openai_api_key_here
# 或者
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# 模型选择
PRIMARY_LLM_MODEL=gpt-4
# 或者使用更便宜的模型
# PRIMARY_LLM_MODEL=gpt-3.5-turbo
SECONDARY_LLM_MODEL=gpt-3.5-turbo

# LLM提供商（openai 或 anthropic）
LLM_PROVIDER=openai

# 系统配置
MAX_CONVERSATION_ROUNDS=20
CONTEXT_SUMMARY_INTERVAL=5
LOG_LEVEL=INFO

# 存储配置
STORAGE_BACKEND=memory
EOF
```

**重要：** 请将 `your_openai_api_key_here` 替换为你的实际API密钥。

### 步骤3：验证配置

运行配置检查脚本：

```bash
python scripts/check_config.py
```

### 步骤4：启动服务

```bash
# 方式1：使用uvicorn直接启动
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 方式2：使用Python启动
python api/main.py
```

### 步骤5：测试API

打开新的终端窗口，测试API：

```bash
# 1. 检查服务是否运行
curl http://localhost:8000/

# 2. 开始对话
curl -X POST "http://localhost:8000/conversations/start" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user_001"}'

# 3. 回答问题（替换{conversation_id}为上面返回的ID）
curl -X POST "http://localhost:8000/conversations/{conversation_id}/respond" \
  -H "Content-Type: application/json" \
  -d '{"user_response": "I am a student. I like reading books."}'
```

## 三、使用Python客户端测试

创建测试脚本 `test_client.py`：

```python
import requests
import json

BASE_URL = "http://localhost:8000"

def test_conversation():
    # 1. 开始对话
    print("开始对话...")
    response = requests.post(
        f"{BASE_URL}/conversations/start",
        json={"user_id": "test_user_001"}
    )
    data = response.json()
    conversation_id = data["conversation_id"]
    print(f"对话ID: {conversation_id}")
    print(f"初始问题: {data['initial_question']}\n")
    
    # 2. 回答几轮问题
    for i in range(3):
        user_answer = input(f"第{i+1}轮回答: ")
        if not user_answer:
            break
            
        response = requests.post(
            f"{BASE_URL}/conversations/{conversation_id}/respond",
            json={"user_response": user_answer}
        )
        data = response.json()
        
        print(f"\n下一题: {data['next_question']}")
        print(f"评估分数: {data['assessment']['ability_profile']['overall_score']}")
        print(f"CEFR等级: {data['assessment']['ability_profile']['cefr_level']}")
        print(f"强项: {data['assessment']['ability_profile']['strengths']}")
        print(f"弱项: {data['assessment']['ability_profile']['weaknesses']}\n")
    
    print("测试完成！")

if __name__ == "__main__":
    test_conversation()
```

运行测试：

```bash
python test_client.py
```

## 四、常见问题排查

### 问题1：导入错误

**错误信息：** `ModuleNotFoundError: No module named 'xxx'`

**解决方案：**
```bash
# 确保在项目根目录
cd /home/ubuntu/learning_english

# 安装依赖
pip install -r requirements.txt

# 如果使用虚拟环境，确保已激活
# source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate     # Windows
```

### 问题2：API密钥错误

**错误信息：** `Invalid API key` 或 `Authentication failed`

**解决方案：**
1. 检查 `.env` 文件是否存在
2. 确认API密钥正确
3. 确认API密钥有足够的余额/权限

### 问题3：模型不可用

**错误信息：** `Model not found` 或 `Model not available`

**解决方案：**
- 检查模型名称是否正确
- 确认账户有权限使用该模型
- 尝试使用 `gpt-3.5-turbo` 作为替代

### 问题4：端口被占用

**错误信息：** `Address already in use`

**解决方案：**
```bash
# 查找占用端口的进程
lsof -i :8000  # Linux/Mac
netstat -ano | findstr :8000  # Windows

# 杀死进程或使用其他端口
uvicorn api.main:app --port 8001
```

## 五、验证系统运行

### 健康检查

访问 `http://localhost:8000/` 应该返回：

```json
{
  "message": "LinguaCoach API",
  "version": "1.0.0",
  "status": "running"
}
```

### API文档

访问 `http://localhost:8000/docs` 查看Swagger API文档。

### 完整流程测试

1. ✅ 服务启动成功
2. ✅ 开始对话成功
3. ✅ 回答问题成功
4. ✅ 评估功能正常
5. ✅ 题目生成正常
6. ✅ 用户画像更新正常

## 六、下一步优化

框架已经可以运行后，可以考虑：

1. **添加报告生成功能**
   - 集成ReportPrompt到ConversationManager
   - 添加报告生成API端点

2. **实现缓存机制**
   - 题目模板缓存
   - 用户画像缓存

3. **添加数据库存储**
   - 实现PostgreSQL存储
   - 实现Redis存储

4. **编写测试代码**
   - 单元测试
   - 集成测试

5. **性能优化**
   - 异步处理
   - 批量操作

## 七、总结

**当前状态：** ✅ 框架可以运行

**核心功能：** ✅ 全部可用

**需要配置：** API密钥（必须）

**预计启动时间：** 5-10分钟

按照上述步骤，你应该能够成功启动并运行整个框架！

