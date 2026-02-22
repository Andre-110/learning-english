# 兴趣点收集功能状态

## ✅ 已实现的基础功能

### 1. 主题池系统 (`config/topics.py`)
- ✅ `TopicPool` 类管理主题
- ✅ 按 CEFR 等级分类主题（A1-C2）
- ✅ 每个主题包含名称、描述、关键词
- ✅ 支持根据等级获取主题列表

**主题分类**：
- A1: 自我介绍、日常活动、食物偏好
- A2: 周末计划、旅行经历、兴趣爱好
- B1: 环保生活、工作与职业、健康生活
- B2: 人工智能影响、教育系统、全球化
- C1: 经济与政策、科技伦理
- C2: 哲学思辨、复杂社会问题

### 2. 主题提取 (`core/conversation.py`)
- ✅ 从对话中提取已讨论的主题（`previous_topics`）
- ✅ 通过关键词匹配识别主题
- ✅ 传递给问题生成器避免重复

**当前实现**（第176-187行）：
```python
previous_topics = []
for msg in conversation.messages:
    if msg.role == MessageRole.ASSISTANT:
        content_lower = msg.content.lower()
        if "daily life" in content_lower or "morning" in content_lower:
            previous_topics.append("daily life")
        elif "healthy" in content_lower or "fitness" in content_lower:
            previous_topics.append("healthy living")
        elif "environment" in content_lower or "green" in content_lower:
            previous_topics.append("environment")
```

### 3. 主题使用 (`services/generator.py`)
- ✅ 生成问题时使用 `previous_topics` 避免重复
- ✅ 根据用户 CEFR 等级选择适配的主题池
- ✅ 在提示词中包含已讨论主题信息

**提示词集成**（`prompts/templates.py`）：
```python
if previous_topics:
    topics_context = f"\n[已讨论主题]\n已讨论的主题包括: {', '.join(previous_topics[-5:])}\n请避免重复相同主题，或从新角度切入。\n"
```

---

## ⚠️ 需要完善的功能

### 1. 用户兴趣标签持久化存储 ❌

**当前状态**：
- 主题提取是临时的，只在对话过程中使用
- 没有保存到数据库
- 没有用户级别的兴趣画像

**需要实现**：
- [ ] 在 `users` 表中添加 `interests` 字段（JSONB）
- [ ] 从对话中提取用户感兴趣的主题
- [ ] 计算兴趣权重（基于讨论频率、用户反应等）
- [ ] 持久化保存到数据库

**数据库设计**：
```sql
-- 在 users 表中添加字段
ALTER TABLE users ADD COLUMN interests JSONB DEFAULT '[]';
-- 格式: [{"category": "news", "tags": ["technology", "AI"], "weight": 0.8}, ...]

-- 或者新建表 user_interests
CREATE TABLE user_interests (
    interest_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    interest_category VARCHAR(50), -- news, tech, sports, travel等
    interest_tags JSONB DEFAULT '[]',
    weight REAL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
```

### 2. 兴趣匹配度评估 ❌

**当前状态**：
- 没有计算对话内容与用户兴趣的匹配度
- 没有记录匹配的兴趣标签

**需要实现**：
- [ ] 检测对话内容是否涉及用户兴趣
- [ ] 计算兴趣匹配度分数（0-1）
- [ ] 记录匹配的兴趣标签
- [ ] 在 `conversations` 表中存储匹配度

**数据库设计**：
```sql
ALTER TABLE conversations ADD COLUMN interest_match_score REAL DEFAULT 0.0;
ALTER TABLE conversations ADD COLUMN matched_interests JSONB DEFAULT '[]';
```

**代码位置**：
- `services/recommender.py` - 新建推荐服务
- `core/conversation.py` - 对话中检测兴趣匹配

### 3. 基于兴趣的主动推荐 ❌

**当前状态**：
- 只是避免重复主题
- 没有主动推荐用户感兴趣的内容

**需要实现**：
- [ ] 根据用户兴趣标签推荐主题
- [ ] 优先选择用户感兴趣的话题
- [ ] 动态调整推荐权重

**代码位置**：
- `services/recommender.py` - 推荐算法
- `services/generator.py` - 集成推荐逻辑

### 4. 兴趣提取增强 ⚠️

**当前状态**：
- 使用简单的关键词匹配
- 只能识别少数几个主题

**需要改进**：
- [ ] 使用 LLM 提取主题（更准确）
- [ ] 支持多维度兴趣（新闻、科技、体育、旅游等）
- [ ] 从用户回答中提取兴趣（不仅仅是问题）

**代码位置**：
- `services/topic_extractor.py` - 新建主题提取服务
- `core/conversation.py` - 增强主题提取逻辑

---

## 📊 功能对比

| 功能 | 当前状态 | 目标状态 |
|------|---------|---------|
| 主题池管理 | ✅ 已实现 | ✅ 完善 |
| 主题提取 | ⚠️ 基础实现 | ✅ 增强（LLM提取） |
| 避免重复 | ✅ 已实现 | ✅ 完善 |
| 兴趣存储 | ❌ 未实现 | ✅ 持久化存储 |
| 兴趣匹配 | ❌ 未实现 | ✅ 匹配度评估 |
| 主动推荐 | ❌ 未实现 | ✅ 基于兴趣推荐 |

---

## 🎯 下一步实现计划

### 阶段1：完善基础功能
1. 增强主题提取（使用 LLM）
2. 添加用户兴趣存储（数据库）

### 阶段2：实现匹配评估
3. 实现兴趣匹配度计算
4. 记录匹配结果到数据库

### 阶段3：主动推荐
5. 实现基于兴趣的推荐算法
6. 集成到问题生成流程

---

## 📝 相关文件

- `config/topics.py` - 主题池定义
- `core/conversation.py` - 主题提取逻辑
- `services/generator.py` - 主题使用
- `prompts/templates.py` - 提示词模板
- `docs/MISSING_FEATURES.md` - 缺失功能文档

