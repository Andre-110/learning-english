# 存储功能概览

## 📦 存储架构

系统使用**Supabase**作为持久化存储后端，所有数据都会保存到数据库中。

```
┌─────────────────────────────────────┐
│      ConversationManager             │
│      (对话管理器)                    │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       │                 │
┌──────▼──────┐  ┌──────▼──────┐
│ Conversation │  │ UserProfile │
│ Repository   │  │ Repository  │
└──────┬──────┘  └──────┬──────┘
       │                 │
       └────────┬─────────┘
                │
       ┌────────▼────────┐
       │   Supabase      │
       │   Database      │
       └─────────────────┘
```

## 💾 存储的数据

### 1. 对话数据 (`conversations` 表)

**存储内容**:
- `conversation_id`: 对话唯一ID
- `user_id`: 用户ID
- `state`: 对话状态（IN_PROGRESS, COMPLETED等）
- `current_round`: 当前轮次
- `summary`: 对话摘要
- `summary_round`: 摘要轮次
- `started_at`: 开始时间
- `ended_at`: 结束时间
- `metadata`: JSONB字段，存储额外信息
  - `discussed_topics`: 已讨论的主题
  - `matched_interests`: 匹配的兴趣
  - `interest_match_score`: 兴趣匹配分数

**存储时机**: 
- ✅ 每次对话创建时
- ✅ 每次消息添加后（`messages` 表)

**存储内容**:
- `conversation_id`: 所属对话ID
- `round_number`: 轮次编号
- `sender_role`: 发送者角色（user/assistant/system）
- `content`: 消息内容
- `timestamp`: 时间戳
- `metadata`: JSONB字段，存储评估数据
  - `assessment`: 评估结果（快速/完整）
    - `type`: "quick" 或 "full"
    - `ability_profile`: 能力画像
      - `overall_score`: 综合分数
      - `cefr_level`: CEFR等级
      - `strengths`: 强项列表
      - `weaknesses`: 弱项列表
    - `dimension_scores`: 维度评分（完整评估）
    - `round_number`: 轮次
    - `timestamp`: 评估时间
  - `full_assessment`: 完整评估结果（如果存在）

**存储时机**: 
- ✅ 每次消息发送时
- ✅ 评估完成后更新metadata

### 3. 用户画像 (`users` 表)

**存储内容**:
- `user_id`: 用户唯一ID
- `overall_score`: 综合分数（0-100）
- `cefr_level`: CEFR等级（A1-C2）
- `strengths`: 强项列表
- `weaknesses`: 弱项列表
- `interests`: 兴趣标签列表（JSONB）
  - `category`: 兴趣类别
  - `tags`: 具体标签
  - `weight`: 权重
  - `last_discussed`: 最后讨论时间
- `conversation_count`: 对话轮数
- `last_updated`: 最后更新时间
- `metadata`: JSONB字段，存储额外信息

**存储时机**: 
- ✅ 用户首次对话时创建
- ✅ 完整评估完成后更新

### 4. 报告数据

**存储方式**: 
- ⚠️ **报告不直接存储到数据库**
- ✅ 报告通过 `ReportService.generate_learning_report()` 动态生成
- ✅ 报告基于存储的对话、评估和用户画像数据生成

**生成时机**:
- 用户请求报告时
- 对话结束时（可选）

## 🔍 数据查询功能

### ConversationRepository

```python
# 保存对话
conversation_repo.save(conversation)

# 获取对话
conversation = conversation_repo.get(conversation_id)

# 获取用户的所有对话
conversations = conversation_repo.get_by_user(user_id)

# 删除对话
conversation_repo.delete(conversation_id)
```

### UserRepository

```python
# 保存用户画像
user_repo.save(user_profile)

# 获取用户画像
user_profile = user_repo.get(user_id)

# 获取或创建用户画像
user_profile = user_repo.get_or_create(user_id)

# 删除用户
user_repo.delete(user_id)
```

## 📊 数据关系

```
User (用户)
  ├── UserProfile (用户画像)
  │   ├── overall_score
  │   ├── cefr_level
  │   ├── strengths
  │   ├── weaknesses
  │   └── interests[]
  │
  └── Conversations[] (对话列表)
      ├── Conversation (对话)
      │   ├── conversation_id
      │   ├── state
      │   ├── summary
      │   └── Messages[] (消息列表)
      │       ├── Message (消息)
      │       │   ├── role
      │       │   ├── content
      │       │   └── metadata
      │       │       └── assessment (评估数据)
      │       │           ├── type: "quick" | "full"
      │       │           ├── ability_profile
      │       │           └── dimension_scores[]
      │       └── ...
      └── ...
```

## 🔄 数据更新流程

### 对话更新

```
用户发送消息
    ↓
添加消息到对话
    ↓
快速评估（保存到消息metadata）
    ↓
保存对话到数据库
    ├── 更新 conversations 表
    └── 更新/插入 messages 表
    ↓
完整评估完成（更新消息metadata）
    ↓
再次保存对话到数据库
```

### 用户画像更新

```
完整评估完成
    ↓
更新用户画像
    ├── overall_score
    ├── cefr_level
    ├── strengths
    ├── weaknesses
    └── conversation_count++
    ↓
保存用户画像到数据库
    └── 更新 users 表
```

## 📋 评估数据存储

### 快速评估存储

```json
{
  "type": "quick",
  "ability_profile": {
    "overall_score": 25.0,
    "cefr_level": "A1",
    "strengths": ["表达基本意思"],
    "weaknesses": ["语法结构不完整"]
  },
  "confidence": 0.8,
  "round_number": 1,
  "timestamp": "2025-12-10T10:00:00"
}
```

### 完整评估存储

```json
{
  "type": "full",
  "ability_profile": {
    "overall_score": 30.0,
    "cefr_level": "A1",
    "strengths": ["表达基本意思", "使用简单词汇"],
    "weaknesses": ["语法结构不完整", "词汇量有限"]
  },
  "dimension_scores": [
    {
      "dimension": "内容相关性",
      "score": 3.0,
      "comment": "...",
      "reasoning": "..."
    },
    ...
  ],
  "round_number": 1,
  "timestamp": "2025-12-10T10:00:05"
}
```

## 🗄️ 数据库表结构

### conversations 表

```sql
CREATE TABLE conversations (
    conversation_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    state TEXT NOT NULL,
    current_round INTEGER,
    summary TEXT,
    summary_round INTEGER,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    metadata JSONB
);
```

### messages 表

```sql
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(conversation_id),
    round_number INTEGER,
    sender_role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP,
    metadata JSONB
);
```

### users 表

```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    overall_score FLOAT,
    cefr_level TEXT,
    strengths TEXT[],
    weaknesses TEXT[],
    interests JSONB,
    conversation_count INTEGER,
    last_updated TIMESTAMP,
    metadata JSONB
);
```

## ✅ 存储确认

### 已存储的数据

- ✅ **对话历史**: 所有对话和消息都存储在Supabase
  - 测试结果：用户 `user_001` 有 13 个对话
  - 每个对话包含完整的消息列表
  - 对话状态（in_progress, completed等）正常保存
- ✅ **用户画像**: 用户的能力画像、兴趣、对话轮数都存储
  - 测试结果：用户画像存在，包含综合分数、CEFR等级、对话轮数
  - 综合分数：37.75/100
  - CEFR等级：A2
  - 对话轮数：19轮
- ✅ **评估数据**: 快速评估和完整评估都存储在消息metadata中
  - 评估数据存储在消息的 `metadata.assessment` 字段中
  - 包含评估类型（quick/full）、分数、等级、强项、弱项等
- ✅ **对话摘要**: 长对话的摘要存储在conversations表

### 未直接存储的数据

- ⚠️ **报告**: 报告是动态生成的，不直接存储
  - 但可以通过存储的数据随时重新生成
  - 使用 `ConversationManager.end_conversation()` 可以生成报告
- ⚠️ **音频文件**: 音频文件不存储，只存储转录文本
  - 音频通过WebSocket实时传输，不持久化存储
  - 只保存转录后的文本内容

## 🔍 数据查询示例

### 查询用户的所有对话

```python
conversations = conversation_repo.get_by_user("user_001")
for conv in conversations:
    print(f"对话ID: {conv.conversation_id}")
    print(f"消息数: {len(conv.messages)}")
    print(f"状态: {conv.state.value}")
```

### 查询对话的所有评估

```python
conversation = conversation_repo.get(conversation_id)
assessments = []
for msg in conversation.messages:
    if msg.metadata and "assessment" in msg.metadata:
        assess = msg.metadata["assessment"]
        if assess.get("type") == "full":
            assessments.append(assess)
```

### 查询用户画像历史

```python
user_profile = user_repo.get("user_001")
print(f"综合分数: {user_profile.overall_score}")
print(f"CEFR等级: {user_profile.cefr_level.value}")
print(f"对话轮数: {user_profile.conversation_count}")
print(f"兴趣: {[i.category for i in user_profile.interests]}")
```

## 📝 总结

### 存储功能

- ✅ **对话管理**: ConversationManager 管理所有对话
- ✅ **数据持久化**: 使用Supabase存储所有数据
- ✅ **历史对话**: 所有对话和消息都保存
- ✅ **用户画像**: 用户能力画像和兴趣都保存
- ✅ **评估数据**: 快速评估和完整评估都保存在消息metadata中
- ✅ **报告生成**: 基于存储的数据动态生成报告

### 数据完整性

- ✅ 对话数据完整保存
- ✅ 评估数据完整保存（包括快速和完整评估）
- ✅ 用户画像实时更新
- ✅ 所有数据都可以查询和恢复

