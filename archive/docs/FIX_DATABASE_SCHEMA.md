# 数据库Schema修复说明

## 问题
错误信息：`Could not find the 'discussed_topics' column of 'conversations' in the schema cache`

## 原因
代码尝试使用 `discussed_topics`、`matched_interests` 和 `interest_match_score` 字段，但这些字段在数据库表中不存在。

## 解决方案

### 方案1：更新数据库Schema（推荐）
在Supabase Dashboard的SQL Editor中执行以下SQL：

```sql
-- 添加兴趣相关字段到conversations表
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS interest_match_score REAL DEFAULT 0.0;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS matched_interests JSONB DEFAULT '[]';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS discussed_topics JSONB DEFAULT '[]';

-- 添加metadata字段（如果不存在）
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
```

或者直接执行脚本：
```bash
# 查看脚本内容
cat scripts/add_interests_schema.sql

# 然后在Supabase Dashboard中执行
```

### 方案2：使用代码修复（已完成）
代码已经修复，现在会将数据存储在 `metadata` 字段中，而不是独立的字段。这样可以避免字段不存在的问题。

**但是需要重启后端服务才能生效！**

## 重启后端服务

```bash
# 1. 停止当前服务
pkill -f "uvicorn api.main:app"

# 2. 重新启动
cd /home/ubuntu/learning_english
source venv/bin/activate
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## 验证修复

重启后，访问前端页面并点击"开始对话"，应该可以正常工作了。

如果仍有问题，请检查：
1. 后端服务是否正常启动
2. Supabase连接是否正常
3. 浏览器控制台的错误信息



