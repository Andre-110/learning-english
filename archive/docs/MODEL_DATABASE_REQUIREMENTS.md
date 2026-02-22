# 模型和数据库选取要求

## 一、LLM模型选取要求

### 1.1 支持的提供商

系统支持两种LLM提供商：

#### OpenAI
- **状态**：✅ 已实现
- **代码位置**：`services/llm.py` - `OpenAIService`
- **配置**：`LLM_PROVIDER=openai`

#### Anthropic
- **状态**：✅ 已实现
- **代码位置**：`services/llm.py` - `AnthropicService`
- **配置**：`LLM_PROVIDER=anthropic`

### 1.2 OpenAI模型要求

#### 推荐模型

**主要模型（用于评估和生成）：**
- `gpt-4` - 最佳质量，推荐用于生产环境
- `gpt-4-turbo` - 性能与成本平衡
- `gpt-4o` - 最新版本，性能优秀

**辅助模型（用于摘要等辅助任务）：**
- `gpt-3.5-turbo` - 成本低，速度快
- `gpt-4` - 如果需要更高质量

#### 模型能力要求

**评估任务（EvaluatorService）：**
- **必须支持JSON模式**：GPT-4系列、GPT-3.5-turbo-1106+
- **推荐温度**：0.3（保证一致性）
- **最小上下文窗口**：4096 tokens

**生成任务（QuestionGeneratorService）：**
- **推荐温度**：0.8（增加多样性）
- **最小上下文窗口**：4096 tokens
- **支持流式输出**：可选

**摘要任务（ContextManagerService）：**
- **推荐温度**：0.3（保证准确性）
- **最小上下文窗口**：8192 tokens（处理长对话）

#### JSON模式支持

**支持JSON模式的模型：**
- ✅ GPT-4系列（所有版本）
- ✅ GPT-3.5-turbo-1106+
- ❌ GPT-3.5-turbo（旧版本，需依赖提示词）

**代码实现：**
```python
# services/llm.py
if model_name.startswith("gpt-4") or ("gpt-3.5-turbo" in model_name and "1106" in model_name):
    request_kwargs["response_format"] = {"type": "json_object"}
```

### 1.3 Anthropic模型要求

#### 推荐模型

**主要模型：**
- `claude-3-opus-20240229` - 最佳质量
- `claude-3-sonnet-20240229` - 性能与成本平衡
- `claude-3-haiku-20240229` - 快速响应

**模型特点：**
- 所有Claude 3模型都支持JSON输出
- 上下文窗口：200K tokens（远超GPT）
- 适合长对话场景

### 1.4 模型选择建议

#### 场景1：开发测试
```bash
PRIMARY_LLM_MODEL=gpt-3.5-turbo
SECONDARY_LLM_MODEL=gpt-3.5-turbo
LLM_PROVIDER=openai
```
**理由**：成本低，速度快，适合测试

#### 场景2：生产环境（平衡）
```bash
PRIMARY_LLM_MODEL=gpt-4
SECONDARY_LLM_MODEL=gpt-3.5-turbo
LLM_PROVIDER=openai
```
**理由**：评估和生成用GPT-4保证质量，摘要用GPT-3.5降低成本

#### 场景3：高质量要求
```bash
PRIMARY_LLM_MODEL=gpt-4-turbo
SECONDARY_LLM_MODEL=gpt-4
LLM_PROVIDER=openai
```
**理由**：所有任务都用高质量模型

#### 场景4：长对话场景
```bash
PRIMARY_LLM_MODEL=claude-3-opus-20240229
SECONDARY_LLM_MODEL=claude-3-sonnet-20240229
LLM_PROVIDER=anthropic
```
**理由**：Claude的大上下文窗口适合长对话

### 1.5 API密钥要求

#### OpenAI
- **格式**：`sk-...`（以sk-开头）
- **权限**：需要API访问权限
- **配额**：检查账户的rate limit和quota
- **获取地址**：https://platform.openai.com/api-keys

#### Anthropic
- **格式**：`sk-ant-...`（以sk-ant-开头）
- **权限**：需要API访问权限
- **配额**：检查账户的rate limit
- **获取地址**：https://console.anthropic.com/settings/keys

### 1.6 成本考虑

#### OpenAI定价（2024年，仅供参考）

| 模型 | 输入价格 | 输出价格 | 说明 |
|------|---------|---------|------|
| GPT-4 | $0.03/1K tokens | $0.06/1K tokens | 高质量 |
| GPT-4 Turbo | $0.01/1K tokens | $0.03/1K tokens | 性价比高 |
| GPT-3.5 Turbo | $0.0005/1K tokens | $0.0015/1K tokens | 低成本 |

#### 估算成本

**单轮对话成本：**
- 评估：~500 tokens输入 + 200 tokens输出 ≈ $0.02 (GPT-4)
- 生成：~300 tokens输入 + 100 tokens输出 ≈ $0.01 (GPT-4)
- 摘要：~2000 tokens输入 + 200 tokens输出 ≈ $0.07 (GPT-4)

**20轮对话总成本：** 约 $2-5（使用GPT-4）

**降低成本建议：**
- 使用GPT-3.5-turbo进行摘要
- 使用GPT-4只进行关键评估
- 实现缓存机制（题目模板缓存）

## 二、数据库/存储选取要求

### 2.1 支持的存储后端

#### Memory（内存存储）
- **状态**：✅ 已实现
- **代码位置**：`storage/impl/memory_repository.py`
- **配置**：`STORAGE_BACKEND=memory`
- **特点**：
  - 数据存储在内存中
  - 服务重启后数据丢失
  - 适合开发和测试
  - 性能最高

#### Database（数据库）
- **状态**：⚠️ 待实现
- **代码位置**：`storage/impl/`（需要创建）
- **配置**：`STORAGE_BACKEND=database`
- **推荐数据库**：
  - PostgreSQL（关系型，推荐）
  - MySQL/MariaDB（关系型）
  - MongoDB（文档型，适合JSON数据）

#### Redis（缓存+持久化）
- **状态**：⚠️ 待实现
- **代码位置**：`storage/impl/`（需要创建）
- **配置**：`STORAGE_BACKEND=redis`
- **特点**：
  - 高性能缓存
  - 支持持久化
  - 适合高并发场景

### 2.2 存储数据结构要求

#### 对话数据（Conversation）

**必需字段：**
- `conversation_id` (String, Primary Key)
- `user_id` (String, Index)
- `messages` (JSON Array)
- `state` (Enum: INITIALIZING, IN_PROGRESS, COMPLETED, PAUSED)
- `created_at` (DateTime)
- `updated_at` (DateTime)
- `summary` (Text, Optional)
- `summary_round` (Integer, Optional)

**索引要求：**
- `conversation_id` - 主键
- `user_id` - 用于查询用户的所有对话
- `created_at` - 用于排序和查询

**存储大小估算：**
- 单条消息：~100-500 bytes
- 20轮对话：~10-50 KB
- 1000个对话：~10-50 MB

#### 用户画像（UserProfile）

**必需字段：**
- `user_id` (String, Primary Key)
- `overall_score` (Float, 0-100)
- `cefr_level` (Enum: A1-C2)
- `strengths` (JSON Array)
- `weaknesses` (JSON Array)
- `conversation_count` (Integer)
- `last_updated` (DateTime)

**索引要求：**
- `user_id` - 主键
- `cefr_level` - 用于统计分析
- `last_updated` - 用于查询活跃用户

**存储大小估算：**
- 单个用户画像：~500 bytes
- 10000个用户：~5 MB

#### 评估历史（Assessment）

**可选表结构：**
- `assessment_id` (String, Primary Key)
- `conversation_id` (String, Foreign Key)
- `round_number` (Integer)
- `dimension_scores` (JSON)
- `ability_profile` (JSON)
- `timestamp` (DateTime)

**索引要求：**
- `conversation_id` - 外键
- `timestamp` - 用于时间序列分析

### 2.3 PostgreSQL实现要求

#### 数据库版本
- **最低版本**：PostgreSQL 12+
- **推荐版本**：PostgreSQL 14+

#### 必需扩展
```sql
-- JSON支持（PostgreSQL原生支持）
-- 索引支持
CREATE EXTENSION IF NOT EXISTS btree_gin;
```

#### 表结构设计

```sql
-- 对话表
CREATE TABLE conversations (
    conversation_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    messages JSONB NOT NULL,
    state VARCHAR(50) NOT NULL,
    summary TEXT,
    summary_round INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_created_at ON conversations(created_at);
CREATE INDEX idx_conversations_messages ON conversations USING GIN(messages);

-- 用户画像表
CREATE TABLE user_profiles (
    user_id VARCHAR(255) PRIMARY KEY,
    overall_score FLOAT DEFAULT 0.0,
    cefr_level VARCHAR(10) DEFAULT 'A1',
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    conversation_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_profiles_cefr_level ON user_profiles(cefr_level);
CREATE INDEX idx_user_profiles_last_updated ON user_profiles(last_updated);
```

#### 连接配置

```python
# 需要在.env中添加
DATABASE_URL=postgresql://user:password@localhost:5432/lingua_coach
```

### 2.4 MongoDB实现要求

#### 数据库版本
- **最低版本**：MongoDB 4.4+
- **推荐版本**：MongoDB 6.0+

#### 集合设计

```python
# conversations集合
{
    "_id": "conversation_id",
    "user_id": "user123",
    "messages": [...],
    "state": "in_progress",
    "summary": "...",
    "summary_round": 5,
    "created_at": ISODate("..."),
    "updated_at": ISODate("...")
}

# user_profiles集合
{
    "_id": "user_id",
    "overall_score": 72.5,
    "cefr_level": "B1",
    "strengths": [...],
    "weaknesses": [...],
    "conversation_count": 10,
    "last_updated": ISODate("...")
}
```

#### 索引要求

```javascript
// conversations集合索引
db.conversations.createIndex({ "user_id": 1 });
db.conversations.createIndex({ "created_at": -1 });

// user_profiles集合索引
db.user_profiles.createIndex({ "cefr_level": 1 });
db.user_profiles.createIndex({ "last_updated": -1 });
```

#### 连接配置

```python
# 需要在.env中添加
MONGODB_URL=mongodb://user:password@localhost:27017/lingua_coach
```

### 2.5 Redis实现要求

#### 版本要求
- **最低版本**：Redis 6.0+
- **推荐版本**：Redis 7.0+

#### 数据结构设计

```python
# 对话数据（Hash）
conversation:{conversation_id} = {
    "user_id": "...",
    "messages": "[...]",  # JSON字符串
    "state": "...",
    ...
}

# 用户画像（Hash）
user:{user_id} = {
    "overall_score": "72.5",
    "cefr_level": "B1",
    ...
}

# 索引（Set）
user:{user_id}:conversations = {conversation_id1, conversation_id2, ...}
```

#### 持久化配置

```conf
# redis.conf
save 900 1      # 900秒内至少1个key变化则保存
save 300 10     # 300秒内至少10个key变化则保存
save 60 10000   # 60秒内至少10000个key变化则保存
```

#### 连接配置

```python
# 需要在.env中添加
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_password
REDIS_DB=0
```

### 2.6 存储选择建议

#### 开发/测试环境
- **推荐**：Memory（内存存储）
- **理由**：简单快速，无需额外配置

#### 小规模生产（<1000用户）
- **推荐**：PostgreSQL
- **理由**：稳定可靠，易于维护

#### 中等规模（1000-10000用户）
- **推荐**：PostgreSQL + Redis
- **理由**：PostgreSQL持久化，Redis缓存提升性能

#### 大规模（>10000用户）
- **推荐**：MongoDB + Redis
- **理由**：MongoDB水平扩展，Redis高性能缓存

## 三、配置示例

### 3.1 开发环境配置

```bash
# .env
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
PRIMARY_LLM_MODEL=gpt-3.5-turbo
SECONDARY_LLM_MODEL=gpt-3.5-turbo
STORAGE_BACKEND=memory
```

### 3.2 生产环境配置（PostgreSQL）

```bash
# .env
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
PRIMARY_LLM_MODEL=gpt-4
SECONDARY_LLM_MODEL=gpt-3.5-turbo
STORAGE_BACKEND=database
DATABASE_URL=postgresql://user:password@localhost:5432/lingua_coach
```

### 3.3 高性能配置（Redis）

```bash
# .env
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
PRIMARY_LLM_MODEL=gpt-4-turbo
SECONDARY_LLM_MODEL=gpt-3.5-turbo
STORAGE_BACKEND=redis
REDIS_HOST=localhost
REDIS_PORT=6379
```

## 四、性能要求

### 4.1 LLM API性能

**响应时间要求：**
- 评估调用：< 5秒
- 生成调用：< 3秒
- 摘要调用：< 10秒

**并发要求：**
- 支持多用户并发
- 建议使用异步请求（已实现）

### 4.2 数据库性能

**查询性能要求：**
- 单次查询：< 100ms
- 批量查询：< 500ms

**写入性能要求：**
- 单次写入：< 50ms
- 批量写入：< 200ms

## 五、总结

### 模型选择
- **开发**：GPT-3.5-turbo（低成本）
- **生产**：GPT-4（高质量）或GPT-4-turbo（平衡）
- **长对话**：Claude 3（大上下文）

### 存储选择
- **开发**：Memory（简单）
- **生产**：PostgreSQL（稳定）
- **高性能**：Redis + PostgreSQL（缓存+持久化）





