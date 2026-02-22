# 数据库迁移完成

## ✅ 已完成的工作

### 1. 创建 Supabase 存储实现

**文件**: `storage/impl/supabase_repository.py`

实现了两个存储类：
- `SupabaseConversationRepository` - 对话存储
- `SupabaseUserRepository` - 用户存储

**功能**：
- ✅ 保存对话和消息到数据库
- ✅ 从数据库读取对话和消息
- ✅ 保存和更新用户画像
- ✅ 支持批量消息插入
- ✅ 处理时间戳转换
- ✅ 错误处理

### 2. 更新存储工厂

**文件**: `storage/repository.py`

- ✅ 添加了 `supabase` 后端支持
- ✅ `RepositoryFactory.create_repositories(backend="supabase")` 现在可以创建 Supabase 存储实例

### 3. 更新配置

**文件**: `config/settings.py`

- ✅ 添加了 `supabase_url` 和 `supabase_key` 配置项
- ✅ 更新了 `storage_backend` 说明，支持 `supabase`

**文件**: `.env`

- ✅ 添加了 Supabase 配置
- ✅ 设置 `STORAGE_BACKEND=supabase`

### 4. 代码替换

所有使用内存存储的地方现在都通过配置自动切换到数据库：

- ✅ `api/main.py` - 使用 `settings.storage_backend` 创建存储实例
- ✅ `core/conversation.py` - 通过依赖注入使用存储，无需修改
- ✅ 所有测试脚本 - 自动使用配置的存储后端

## 📋 使用步骤

### 步骤 1：创建数据库表

在 Supabase Dashboard > SQL Editor 中执行 `scripts/supabase_schema.sql`

### 步骤 2：配置环境变量

确保 `.env` 文件中包含：

```env
STORAGE_BACKEND=supabase
SUPABASE_URL=https://uxnqqkuviqlptltcepat.supabase.co
SUPABASE_KEY=your_supabase_key
```

### 步骤 3：重启服务

```bash
# 如果服务正在运行，需要重启
pkill -f uvicorn
source venv/bin/activate
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 步骤 4：测试

```bash
python3 test/test_supabase_integration.py
```

## 🔄 切换回内存存储

如果需要临时切换回内存存储（用于测试），只需修改 `.env`：

```env
STORAGE_BACKEND=memory
```

## 📊 数据模型映射

### Conversation → conversations 表

| Conversation 字段 | 数据库字段 | 说明 |
|------------------|-----------|------|
| conversation_id | conversation_id | 主键 |
| user_id | user_id | 外键 |
| state | state | 状态枚举值 |
| messages | messages 表 | 关联表 |
| summary | summary | 文本 |
| summary_round | summary_round | 整数 |
| created_at | started_at | 时间戳 |
| updated_at | ended_at | 时间戳（完成时） |

### Message → messages 表

| Message 字段 | 数据库字段 | 说明 |
|-------------|-----------|------|
| role | sender_role | 角色枚举值 |
| content | content | 文本 |
| timestamp | timestamp | 时间戳 |
| metadata | metadata | JSONB |

### UserProfile → users 表

| UserProfile 字段 | 数据库字段 | 说明 |
|-----------------|-----------|------|
| user_id | user_id | 主键 |
| overall_score | overall_score | 浮点数 |
| cefr_level | cefr_level | 字符串枚举 |
| strengths | strengths | JSONB 数组 |
| weaknesses | weaknesses | JSONB 数组 |
| conversation_count | conversation_count | 整数 |

## ⚠️ 注意事项

1. **表必须先创建**：在使用 Supabase 存储之前，必须先在 Supabase Dashboard 中执行 SQL 脚本创建表。

2. **时间戳处理**：代码会自动处理 ISO 格式时间戳的转换，包括时区处理。

3. **消息轮次**：消息的 `round_number` 是根据消息顺序自动计算的（每轮包含 user 和 assistant 消息）。

4. **批量操作**：保存对话时会批量插入消息，提高性能。

5. **错误处理**：如果表不存在或操作失败，会抛出异常，需要检查数据库连接和表结构。

## 🧪 测试

运行集成测试：

```bash
python3 test/test_supabase_integration.py
```

测试包括：
- ✅ 用户创建和读取
- ✅ 用户画像更新
- ✅ 对话创建和保存
- ✅ 消息保存和读取
- ✅ 对话更新
- ✅ 用户对话列表查询

## 📝 相关文件

- `storage/impl/supabase_repository.py` - Supabase 存储实现
- `storage/repository.py` - 存储工厂
- `config/settings.py` - 配置管理
- `scripts/supabase_schema.sql` - 数据库表结构
- `test/test_supabase_integration.py` - 集成测试

