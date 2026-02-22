# 数据库表结构说明

## 📊 数据库概览

系统共有 **7 张表**，用于存储英语学习对话评估系统的所有数据。

---

## 1. users（用户表）

### 作用
存储用户的基本信息和能力画像，包括 CEFR 等级、综合分数、强项弱项等。

### 表结构

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `user_id` | VARCHAR(255) | PRIMARY KEY | 用户唯一标识 |
| `username` | VARCHAR(255) | UNIQUE NOT NULL | 用户名 |
| `email` | VARCHAR(255) | UNIQUE | 邮箱地址 |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | 创建时间 |
| `last_login_at` | TIMESTAMPTZ | DEFAULT NOW() | 最后登录时间 |
| `overall_score` | REAL | DEFAULT 0.0 | 综合能力分数（0-100） |
| `cefr_level` | VARCHAR(10) | DEFAULT 'A1' | CEFR等级（A1-C2） |
| `strengths` | JSONB | DEFAULT '[]' | 强项列表，如 ["内容相关性", "语言准确性"] |
| `weaknesses` | JSONB | DEFAULT '[]' | 弱项列表，如 ["交互深度", "词汇丰富度"] |
| `conversation_count` | INT | DEFAULT 0 | 总对话轮数 |
| `metadata` | JSONB | DEFAULT '{}' | 额外的用户元数据 |

### 索引
- `idx_users_cefr_level` - CEFR等级索引
- `idx_users_overall_score` - 综合分数索引

### 示例数据
```json
{
  "user_id": "user_001",
  "username": "alice_student",
  "email": "alice@example.com",
  "overall_score": 65.5,
  "cefr_level": "B1",
  "strengths": ["内容相关性", "语言准确性"],
  "weaknesses": ["交互深度", "词汇丰富度"],
  "conversation_count": 5
}
```

---

## 2. conversations（对话会话表）

### 作用
存储对话会话的基本信息，包括状态、摘要、轮次等。

### 表结构

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `conversation_id` | VARCHAR(255) | PRIMARY KEY | 对话唯一标识 |
| `user_id` | VARCHAR(255) | NOT NULL, FK → users | 用户ID（外键） |
| `started_at` | TIMESTAMPTZ | DEFAULT NOW() | 对话开始时间 |
| `ended_at` | TIMESTAMPTZ | NULL | 对话结束时间 |
| `state` | VARCHAR(50) | DEFAULT 'IN_PROGRESS' | 状态：IN_PROGRESS, COMPLETED, PAUSED |
| `current_round` | INT | DEFAULT 0 | 当前对话轮次 |
| `summary` | TEXT | NULL | 对话摘要（用于上下文压缩） |
| `summary_round` | INT | DEFAULT 0 | 摘要对应的轮数 |

### 索引
- `idx_conversations_user_id` - 用户ID索引
- `idx_conversations_state` - 状态索引

### 外键关系
- `user_id` → `users.user_id` (ON DELETE CASCADE)

### 示例数据
```json
{
  "conversation_id": "conv_001",
  "user_id": "user_001",
  "state": "COMPLETED",
  "current_round": 3,
  "summary": "讨论了日常活动和健康习惯，用户表现出良好的语言基础。"
}
```

---

## 3. messages（消息表）

### 作用
存储对话中的每条消息，包括用户输入和助手回复。

### 表结构

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `message_id` | SERIAL | PRIMARY KEY | 消息ID（自增） |
| `conversation_id` | VARCHAR(255) | NOT NULL, FK → conversations | 对话ID（外键） |
| `round_number` | INT | NOT NULL | 消息所属的轮次 |
| `sender_role` | VARCHAR(50) | NOT NULL | 发送者角色：user, assistant |
| `content` | TEXT | NOT NULL | 消息内容 |
| `timestamp` | TIMESTAMPTZ | DEFAULT NOW() | 消息时间戳 |
| `metadata` | JSONB | DEFAULT '{}' | 消息元数据（如评估结果、转录信息等） |

### 索引
- `idx_messages_conversation_id` - 对话ID索引
- `idx_messages_round_number` - 轮次索引（复合索引：conversation_id + round_number）

### 外键关系
- `conversation_id` → `conversations.conversation_id` (ON DELETE CASCADE)

### 示例数据
```json
{
  "message_id": 1,
  "conversation_id": "conv_001",
  "round_number": 1,
  "sender_role": "assistant",
  "content": "Hello! Let's talk about your daily activities.",
  "timestamp": "2025-12-07T06:00:00Z"
}
```

---

## 4. assessments（评估结果表）

### 作用
存储每轮对话的评估结果，包括综合分数、CEFR等级、维度评分等。

### 表结构

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `assessment_id` | SERIAL | PRIMARY KEY | 评估ID（自增） |
| `conversation_id` | VARCHAR(255) | NOT NULL, FK → conversations | 对话ID（外键） |
| `user_id` | VARCHAR(255) | NOT NULL, FK → users | 用户ID（外键） |
| `round_number` | INT | NOT NULL | 评估轮次 |
| `overall_score` | REAL | NOT NULL | 综合分数（0-100） |
| `cefr_level` | VARCHAR(10) | NOT NULL | CEFR等级 |
| `strengths` | JSONB | DEFAULT '[]' | 强项列表 |
| `weaknesses` | JSONB | DEFAULT '[]' | 弱项列表 |
| `dimension_scores` | JSONB | DEFAULT '[]' | 维度评分列表，包含5个维度 |
| `raw_llm_response` | JSONB | DEFAULT '{}' | LLM原始响应（用于调试） |
| `timestamp` | TIMESTAMPTZ | DEFAULT NOW() | 评估时间 |

### 索引
- `idx_assessments_conversation_id` - 对话ID索引
- `idx_assessments_user_id` - 用户ID索引
- `idx_assessments_round_number` - 轮次索引（复合索引）

### 外键关系
- `conversation_id` → `conversations.conversation_id` (ON DELETE CASCADE)
- `user_id` → `users.user_id` (ON DELETE CASCADE)

### dimension_scores 结构示例
```json
[
  {"dimension": "内容相关性", "score": 4.5},
  {"dimension": "语言准确性", "score": 4.0},
  {"dimension": "表达流利度", "score": 3.5},
  {"dimension": "交互深度", "score": 3.0},
  {"dimension": "词汇丰富度", "score": 3.0}
]
```

---

## 5. learning_reports（学习报告表）

### 作用
存储为用户生成的学习报告，包括能力分析、进步轨迹、学习建议等。

### 表结构

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `report_id` | SERIAL | PRIMARY KEY | 报告ID（自增） |
| `user_id` | VARCHAR(255) | NOT NULL, FK → users | 用户ID（外键） |
| `conversation_id` | VARCHAR(255) | NULL, FK → conversations | 对话ID（外键，可选） |
| `generated_at` | TIMESTAMPTZ | DEFAULT NOW() | 报告生成时间 |
| `report_content` | TEXT | NOT NULL | 报告内容（Markdown格式） |

### 索引
- `idx_learning_reports_user_id` - 用户ID索引

### 外键关系
- `user_id` → `users.user_id` (ON DELETE CASCADE)
- `conversation_id` → `conversations.conversation_id` (ON DELETE SET NULL)

### report_content 示例
```markdown
# 学习报告

## 能力分析
- **当前CEFR等级**：B1（中级水平）
- **综合分数**：54.25/100

## 进步轨迹
- 第1轮：45.5分 (A2)
- 第2轮：54.25分 (B1)

## 强项
- 内容相关性
- 语言准确性

## 弱项
- 交互深度
- 词汇丰富度

## 学习建议
1. 增加词汇量练习
2. 提高对话深度
3. 多练习复杂句式
```

---

## 6. audio_files（音频文件表）

### 作用
存储音频文件的信息，用于语音输入功能。

### 表结构

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `audio_id` | SERIAL | PRIMARY KEY | 音频ID（自增） |
| `message_id` | INT | UNIQUE, FK → messages | 关联的消息ID（外键，可选） |
| `file_path` | VARCHAR(512) | NOT NULL | 文件存储路径 |
| `file_name` | VARCHAR(255) | NOT NULL | 文件名 |
| `file_size_bytes` | BIGINT | NULL | 文件大小（字节） |
| `mime_type` | VARCHAR(100) | NULL | MIME类型（如 audio/mpeg） |
| `uploaded_at` | TIMESTAMPTZ | DEFAULT NOW() | 上传时间 |

### 索引
- `idx_audio_files_message_id` - 消息ID索引

### 外键关系
- `message_id` → `messages.message_id` (ON DELETE SET NULL)

---

## 7. user_progress（用户学习进度表）

### 作用
存储用户在不同技能领域和主题的学习进度。

### 表结构

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `progress_id` | SERIAL | PRIMARY KEY | 进度ID（自增） |
| `user_id` | VARCHAR(255) | NOT NULL, FK → users | 用户ID（外键） |
| `skill_area` | VARCHAR(255) | NULL | 技能领域（如 Grammar, Vocabulary） |
| `topic_area` | VARCHAR(255) | NULL | 主题领域（如 Daily Life, Work） |
| `latest_score` | REAL | NULL | 最新分数 |
| `latest_cefr_level` | VARCHAR(10) | NULL | 最新CEFR等级 |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | 更新时间 |

### 索引
- `idx_user_progress_user_id` - 用户ID索引

### 唯一约束
- `UNIQUE (user_id, skill_area, topic_area)` - 每个用户每个技能领域和主题的组合唯一

### 外键关系
- `user_id` → `users.user_id` (ON DELETE CASCADE)

### 示例数据
```json
{
  "user_id": "user_001",
  "skill_area": "Grammar",
  "topic_area": "Daily Life",
  "latest_score": 54.25,
  "latest_cefr_level": "B1"
}
```

---

## 📈 表关系图

```
users (用户)
  ├── conversations (对话) [1:N]
  │     ├── messages (消息) [1:N]
  │     │     └── audio_files (音频文件) [1:1]
  │     ├── assessments (评估) [1:N]
  │     └── learning_reports (报告) [1:N]
  ├── learning_reports (报告) [1:N]
  └── user_progress (学习进度) [1:N]
```

## 🔑 主要关系说明

1. **用户 → 对话**：一个用户可以有多个对话会话
2. **对话 → 消息**：一个对话包含多条消息
3. **对话 → 评估**：每轮对话都会产生评估结果
4. **用户 → 报告**：一个用户可以有多份学习报告
5. **用户 → 进度**：一个用户在不同技能领域和主题都有学习进度记录
6. **消息 → 音频**：一条消息可以关联一个音频文件（语音输入）

## 📝 数据流转示例

1. **用户开始对话** → 创建 `conversations` 记录
2. **用户发送消息** → 创建 `messages` 记录（如果语音输入，同时创建 `audio_files`）
3. **系统评估回复** → 创建 `assessments` 记录
4. **更新用户画像** → 更新 `users` 表的分数和等级
5. **对话结束** → 生成 `learning_reports`，更新 `user_progress`

## 🎯 使用场景

- **用户画像管理**：通过 `users` 表跟踪用户能力变化
- **对话历史**：通过 `conversations` 和 `messages` 表保存完整对话记录
- **评估分析**：通过 `assessments` 表分析用户进步轨迹
- **学习报告**：通过 `learning_reports` 表生成个性化学习建议
- **进度跟踪**：通过 `user_progress` 表跟踪不同领域的进步

