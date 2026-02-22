# Supabase 数据库设置指南

## 步骤1：在 Supabase Dashboard 中创建表

1. 登录 Supabase Dashboard: https://supabase.com/dashboard
2. 选择项目：`uxnqqkuviqlptltcepat`
3. 进入 **SQL Editor**
4. 复制 `scripts/supabase_schema.sql` 文件中的所有 SQL 语句
5. 粘贴到 SQL Editor 中并执行

## 步骤2：运行 Python 脚本插入模拟数据

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
python3 scripts/setup_supabase.py
```

当提示是否插入模拟数据时，输入 `y`。

## 数据库表结构

### 1. users（用户表）
- `user_id` - 用户ID（主键）
- `username` - 用户名
- `email` - 邮箱
- `overall_score` - 综合分数
- `cefr_level` - CEFR等级
- `strengths` - 强项（JSONB）
- `weaknesses` - 弱项（JSONB）
- `conversation_count` - 对话轮数

### 2. conversations（对话会话表）
- `conversation_id` - 对话ID（主键）
- `user_id` - 用户ID（外键）
- `state` - 状态（IN_PROGRESS, COMPLETED等）
- `current_round` - 当前轮次
- `summary` - 对话摘要

### 3. messages（消息表）
- `message_id` - 消息ID（主键，自增）
- `conversation_id` - 对话ID（外键）
- `round_number` - 轮次号
- `sender_role` - 发送者角色（user, assistant）
- `content` - 消息内容
- `timestamp` - 时间戳

### 4. assessments（评估结果表）
- `assessment_id` - 评估ID（主键，自增）
- `conversation_id` - 对话ID（外键）
- `user_id` - 用户ID（外键）
- `round_number` - 轮次号
- `overall_score` - 综合分数
- `cefr_level` - CEFR等级
- `strengths` - 强项（JSONB）
- `weaknesses` - 弱项（JSONB）
- `dimension_scores` - 维度评分（JSONB）

### 5. learning_reports（学习报告表）
- `report_id` - 报告ID（主键，自增）
- `user_id` - 用户ID（外键）
- `conversation_id` - 对话ID（外键，可选）
- `report_content` - 报告内容（Markdown格式）
- `generated_at` - 生成时间

### 6. audio_files（音频文件表）
- `audio_id` - 音频ID（主键，自增）
- `message_id` - 消息ID（外键，可选）
- `file_path` - 文件路径
- `file_name` - 文件名
- `file_size_bytes` - 文件大小
- `mime_type` - MIME类型

### 7. user_progress（用户学习进度表）
- `progress_id` - 进度ID（主键，自增）
- `user_id` - 用户ID（外键）
- `skill_area` - 技能领域
- `topic_area` - 主题领域
- `latest_score` - 最新分数
- `latest_cefr_level` - 最新CEFR等级

## 模拟数据

脚本会插入以下模拟数据：

- **3个测试用户**（user_001, user_002, user_003）
- **3个对话会话**（conv_001, conv_002, conv_003）
- **多条消息记录**
- **评估结果**
- **学习报告**
- **用户进度记录**

## 验证数据

在 Supabase Dashboard > Table Editor 中查看插入的数据。

## 相关文件

- `scripts/supabase_schema.sql` - SQL 表结构脚本
- `scripts/setup_supabase.py` - Python 设置脚本

