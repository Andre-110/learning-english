# 缺失功能分析报告

## 📋 产品目标回顾

基于 AI Agent 技术，开发一款轻量级英语学习助手，通过个性化内容推荐和交互式学习体验，帮助用户在碎片化时间中提升英语能力。

### 核心功能
1. **能力快速对齐** - 3分钟智能对话评估
2. **兴趣点匹配** - 多维度兴趣标签，个性化内容推荐
3. **交互模式设计** - 对话、听力、阅读多种模式

---

## ❌ 缺失功能清单

### 1. 兴趣点匹配系统 ⚠️ **重要**

**当前状态**：⚠️ **部分实现**（基础框架已有，需要完善）

**已实现**：
- ✅ 主题池系统（`config/topics.py`）- 按 CEFR 等级分类的主题库
- ✅ 主题提取（`core/conversation.py`）- 从对话中提取已讨论主题
- ✅ 避免重复（`services/generator.py`）- 生成问题时避免重复主题

**需要完善**：
- [ ] 用户兴趣标签持久化存储（当前只是临时提取）
- [ ] 兴趣匹配度评估（计算对话与用户兴趣的匹配度）
- [ ] 基于兴趣的主动推荐（优先推荐用户感兴趣的内容）
- [ ] 增强主题提取（使用 LLM 更准确提取，支持多维度兴趣）

**数据库设计**：
```sql
-- 需要新增表：user_interests（用户兴趣表）
CREATE TABLE user_interests (
    interest_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    interest_category VARCHAR(50), -- news, tech, sports, travel等
    interest_tags JSONB DEFAULT '[]', -- 具体标签
    weight REAL DEFAULT 1.0, -- 兴趣权重
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
```

**代码位置**：
- `models/user.py` - 添加 `interests` 字段
- `services/recommender.py` - 新建推荐服务
- `core/conversation.py` - 集成兴趣匹配

---

### 2. 评估速度指标 ⚠️ **重要**

**当前状态**：❌ 未实现

**需要实现**：
- [ ] 记录评估开始时间
- [ ] 记录评估结束时间
- [ ] 计算评估耗时
- [ ] 存储到数据库
- [ ] 统计平均评估时间

**数据库设计**：
```sql
-- 在 assessments 表中添加字段
ALTER TABLE assessments ADD COLUMN evaluation_time_ms INT; -- 评估耗时（毫秒）
ALTER TABLE assessments ADD COLUMN evaluation_started_at TIMESTAMPTZ;
```

**代码位置**：
- `services/evaluator.py` - 添加时间记录
- `models/assessment.py` - 添加时间字段

---

### 3. 兴趣点匹配度指标 ⚠️ **重要**

**当前状态**：❌ 未实现

**需要实现**：
- [ ] 检测对话内容是否涉及用户兴趣
- [ ] 计算兴趣匹配度（0-1）
- [ ] 记录匹配的兴趣标签
- [ ] 统计兴趣匹配率

**数据库设计**：
```sql
-- 在 conversations 表中添加字段
ALTER TABLE conversations ADD COLUMN interest_match_score REAL DEFAULT 0.0; -- 兴趣匹配度
ALTER TABLE conversations ADD COLUMN matched_interests JSONB DEFAULT '[]'; -- 匹配的兴趣标签
```

**代码位置**：
- `services/recommender.py` - 兴趣匹配算法
- `core/conversation.py` - 对话中检测兴趣

---

### 4. 对话连续性指标 ⚠️ **重要**

**当前状态**：⚠️ 部分实现（有上下文管理，但缺少连贯性评估）

**需要实现**：
- [ ] 上下文连贯性评分（0-1）
- [ ] 话题转换自然度评估
- [ ] 前后文关联度分析
- [ ] 记录连贯性分数

**数据库设计**：
```sql
-- 在 conversations 表中添加字段
ALTER TABLE conversations ADD COLUMN coherence_score REAL DEFAULT 0.0; -- 连贯性分数
ALTER TABLE conversations ADD COLUMN topic_transitions JSONB DEFAULT '[]'; -- 话题转换记录
```

**代码位置**：
- `services/context.py` - 增强连贯性分析
- `core/conversation.py` - 对话中评估连贯性

---

### 5. 情绪价值指标 ⚠️ **重要**

**当前状态**：❌ 未实现

**需要实现**：
- [ ] 情感分析（正面/中性/负面）
- [ ] 情绪价值评分（0-1）
- [ ] 用户满意度预测
- [ ] 记录情绪指标

**数据库设计**：
```sql
-- 在 conversations 表中添加字段
ALTER TABLE conversations ADD COLUMN sentiment_score REAL DEFAULT 0.0; -- 情绪分数（-1到1）
ALTER TABLE conversations ADD COLUMN emotion_value REAL DEFAULT 0.0; -- 情绪价值（0-1）

-- 在 messages 表中添加字段
ALTER TABLE messages ADD COLUMN sentiment VARCHAR(20); -- positive, neutral, negative
```

**代码位置**：
- `services/sentiment.py` - 新建情感分析服务
- `core/conversation.py` - 对话中分析情绪

---

### 6. 用户反馈系统 ⚠️ **重要**

**当前状态**：❌ 未实现

**需要实现**：
- [ ] 用户评价收集（点赞/点踩）
- [ ] 反馈原因收集
- [ ] 反馈存储和分析
- [ ] 反馈统计报表

**数据库设计**：
```sql
-- 新建表：user_feedback（用户反馈表）
CREATE TABLE user_feedback (
    feedback_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    conversation_id VARCHAR(255),
    feedback_type VARCHAR(20), -- like, dislike, report
    feedback_reason TEXT, -- 反馈原因
    rating INT, -- 1-5星评分
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE SET NULL
);
```

**代码位置**：
- `api/feedback_endpoint.py` - 新建反馈API
- `models/feedback.py` - 反馈模型

---

### 7. 用户留存指标 ⚠️ **重要**

**当前状态**：⚠️ 部分实现（有用户表，但缺少留存分析）

**需要实现**：
- [ ] 用户活跃度追踪
- [ ] 次日留存率计算
- [ ] 流失原因收集
- [ ] 留存分析报表

**数据库设计**：
```sql
-- 在 users 表中添加字段
ALTER TABLE users ADD COLUMN last_active_at TIMESTAMPTZ; -- 最后活跃时间
ALTER TABLE users ADD COLUMN retention_score REAL DEFAULT 0.0; -- 留存分数
ALTER TABLE users ADD COLUMN churn_reason TEXT; -- 流失原因

-- 新建表：user_sessions（用户会话表）
CREATE TABLE user_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    session_started_at TIMESTAMPTZ DEFAULT NOW(),
    session_ended_at TIMESTAMPTZ,
    session_duration_seconds INT,
    conversations_count INT DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
```

**代码位置**：
- `services/retention.py` - 新建留存分析服务
- `api/analytics_endpoint.py` - 分析API

---

### 8. 系统性能监控 ⚠️ **重要**

**当前状态**：⚠️ 部分实现（有日志，但缺少结构化性能指标）

**需要实现**：
- [ ] API响应时间记录
- [ ] 卡顿检测和记录
- [ ] 网络错误追踪
- [ ] 性能指标统计
- [ ] 性能告警

**数据库设计**：
```sql
-- 新建表：system_metrics（系统指标表）
CREATE TABLE system_metrics (
    metric_id SERIAL PRIMARY KEY,
    metric_type VARCHAR(50), -- api_latency, error_rate, network_error等
    metric_value REAL, -- 指标值
    metric_unit VARCHAR(20), -- ms, count, percent等
    endpoint VARCHAR(255), -- API端点
    user_id VARCHAR(255), -- 用户ID（可选）
    error_message TEXT, -- 错误信息（如果有）
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 新建表：api_requests（API请求表）
CREATE TABLE api_requests (
    request_id SERIAL PRIMARY KEY,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    user_id VARCHAR(255),
    response_time_ms INT, -- 响应时间（毫秒）
    status_code INT,
    error_type VARCHAR(50), -- timeout, network_error, server_error等
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**代码位置**：
- `middleware/performance.py` - 新建性能中间件
- `services/metrics.py` - 指标收集服务
- `api/analytics_endpoint.py` - 性能分析API

---

## 📊 优先级排序

### P0（必须实现）
1. ✅ **兴趣点匹配系统** - 核心功能
2. ✅ **评估速度指标** - 核心指标
3. ✅ **用户反馈系统** - 核心指标

### P1（重要）
4. ✅ **兴趣点匹配度指标** - 评估指标
5. ✅ **对话连续性指标** - 评估指标
6. ✅ **系统性能监控** - 系统指标

### P2（可选）
7. ✅ **情绪价值指标** - 增强体验
8. ✅ **用户留存指标** - 长期分析

---

## 🎯 实现计划

### 第一阶段：核心功能（P0）
1. 实现兴趣点匹配系统
2. 添加评估速度指标
3. 实现用户反馈系统

### 第二阶段：评估指标（P1）
4. 实现兴趣匹配度评估
5. 增强对话连续性分析
6. 添加系统性能监控

### 第三阶段：增强功能（P2）
7. 实现情绪价值分析
8. 添加用户留存分析

---

## 📝 数据库迁移脚本

需要创建新的数据库迁移脚本来添加这些字段和表。

**文件位置**：`scripts/add_missing_features_schema.sql`

---

## 🔗 相关文件

- `docs/DATABASE_SCHEMA.md` - 当前数据库结构
- `models/user.py` - 用户模型（需要扩展）
- `models/assessment.py` - 评估模型（需要扩展）
- `services/evaluator.py` - 评估服务（需要添加时间记录）
- `core/conversation.py` - 对话管理（需要集成新功能）

