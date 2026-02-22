# 数据库设计文档

## 概述
本文档描述了英语学习对话评估系统的数据库表结构设计。

## 数据库选择
- **推荐**: PostgreSQL（支持JSON类型，性能优秀）
- **备选**: MySQL 5.7+（支持JSON类型）

## 表结构设计

### 1. 用户表 (users)
存储用户基本信息和能力画像。

**主要字段**:
- `user_id`: 用户唯一标识（主键）
- `overall_score`: 综合分数（0-100）
- `cefr_level`: CEFR等级（A1-C2）
- `conversation_count`: 总对话轮数
- `strengths`: 强项列表（JSON数组）
- `weaknesses`: 弱项列表（JSON数组）

**索引**:
- `idx_cefr_level`: CEFR等级索引
- `idx_overall_score`: 分数索引
- `idx_created_at`: 创建时间索引

### 2. 对话表 (conversations)
存储对话会话信息。

**主要字段**:
- `conversation_id`: 对话唯一标识（主键）
- `user_id`: 用户ID（外键）
- `state`: 对话状态（INITIALIZING, IN_PROGRESS, COMPLETED, CANCELLED）
- `summary`: 对话摘要
- `summary_round`: 摘要对应的轮数

**索引**:
- `idx_user_id`: 用户ID索引
- `idx_state`: 状态索引
- `idx_created_at`: 创建时间索引

### 3. 消息表 (messages)
存储对话中的所有消息。

**主要字段**:
- `message_id`: 消息唯一标识（主键，自增）
- `conversation_id`: 对话ID（外键）
- `role`: 消息角色（system, user, assistant）
- `content`: 消息内容
- `sequence_number`: 消息序号
- `metadata`: 元数据（JSON，包含评估结果等）

**索引**:
- `idx_conversation_id`: 对话ID索引
- `idx_sequence_number`: 序号索引（复合索引）

### 4. 评估结果表 (assessments)
存储每轮对话的评估结果。

**主要字段**:
- `assessment_id`: 评估唯一标识（主键，自增）
- `conversation_id`: 对话ID（外键）
- `user_id`: 用户ID（外键）
- `round_number`: 评估轮次
- `overall_score`: 综合分数
- `cefr_level`: CEFR等级
- `dimension_scores`: 维度评分（JSON数组）
- `strengths`: 强项列表（JSON数组）
- `weaknesses`: 弱项列表（JSON数组）
- `raw_response`: LLM原始响应（JSON）

**索引**:
- `idx_conversation_id`: 对话ID索引
- `idx_round_number`: 轮次索引（复合索引）
- `uk_conversation_round`: 唯一约束（对话ID + 轮次）

### 5. 学习报告表 (learning_reports)
存储生成的学习报告。

**主要字段**:
- `report_id`: 报告唯一标识（主键，自增）
- `conversation_id`: 对话ID（外键）
- `user_id`: 用户ID（外键）
- `report_content`: 报告内容（Markdown格式）
- `report_type`: 报告类型（final, progress, custom）

**索引**:
- `idx_conversation_id`: 对话ID索引
- `idx_user_id`: 用户ID索引
- `idx_created_at`: 创建时间索引

### 6. 音频文件表 (audio_files) - 可选
存储语音输入的音频文件信息。

**主要字段**:
- `audio_id`: 音频唯一标识（主键，自增）
- `conversation_id`: 对话ID（外键）
- `message_id`: 关联的消息ID（外键）
- `file_path`: 文件存储路径
- `transcribed_text`: 转录文本
- `transcription_provider`: 转录服务提供商

**索引**:
- `idx_conversation_id`: 对话ID索引
- `idx_message_id`: 消息ID索引

### 7. 用户学习进度表 (user_progress) - 可选
存储用户每日学习进度。

**主要字段**:
- `progress_id`: 进度唯一标识（主键，自增）
- `user_id`: 用户ID（外键）
- `date`: 日期
- `conversation_count`: 当日对话轮数
- `study_duration_minutes`: 学习时长（分钟）

**索引**:
- `idx_user_id`: 用户ID索引
- `idx_date`: 日期索引
- `uk_user_date`: 唯一约束（用户ID + 日期）

## 视图设计

### 1. 用户对话统计视图 (user_conversation_stats)
提供用户对话统计信息，包括：
- 总对话数
- 最后对话时间
- 平均评估分数

### 2. 对话详情视图 (conversation_details)
提供对话的详细信息，包括：
- 消息数量
- 评估数量
- 分数统计（最大、最小、平均）

## 数据关系图

```
users (1) ──< (N) conversations
                │
                ├──< (N) messages
                ├──< (N) assessments
                ├──< (N) learning_reports
                └──< (N) audio_files

users (1) ──< (N) user_progress
```

## 使用建议

1. **JSON字段**: 使用JSON类型存储灵活的结构化数据（如强项、弱项、维度评分）
2. **索引优化**: 根据查询模式添加适当的索引
3. **外键约束**: 使用外键确保数据完整性
4. **级联删除**: 设置适当的级联删除规则
5. **时间戳**: 使用时间戳字段追踪数据创建和更新时间

## 迁移建议

从内存存储迁移到数据库存储时：
1. 创建数据库和表结构
2. 实现数据库Repository实现类
3. 逐步迁移现有数据
4. 更新API端点以使用数据库Repository

