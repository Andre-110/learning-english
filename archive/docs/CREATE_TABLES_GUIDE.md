# 创建 Supabase 数据库表 - 快速指南

## 📋 SQL 脚本已准备好

SQL 文件位置：`scripts/supabase_schema.sql`

## 🚀 执行步骤

### 方法1：Supabase Dashboard（推荐）

1. **访问 Supabase Dashboard**
   - 打开浏览器，访问：https://supabase.com/dashboard
   - 登录并选择项目：`uxnqqkuviqlptltcepat`

2. **进入 SQL Editor**
   - 点击左侧菜单的 **"SQL Editor"**
   - 点击 **"New query"** 按钮

3. **复制并执行 SQL**
   - 打开文件：`scripts/supabase_schema.sql`
   - 复制所有内容（Ctrl+A, Ctrl+C）
   - 粘贴到 SQL Editor 中（Ctrl+V）
   - 点击 **"Run"** 按钮或按 **Ctrl+Enter** 执行

4. **验证执行结果**
   - 应该看到 "Success. No rows returned" 或类似的成功消息
   - 如果看到 "already exists" 错误，说明表已存在，可以忽略

### 方法2：使用脚本助手

运行以下命令，脚本会显示完整的 SQL 内容：

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
python3 scripts/create_tables_dashboard.py
```

## ✅ 验证表是否创建成功

执行以下 SQL 查询（在 SQL Editor 中）：

```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

应该看到以下 7 个表：
- `assessments`
- `audio_files`
- `conversations`
- `learning_reports`
- `messages`
- `user_progress`
- `users`

## 🧪 测试数据库连接

表创建完成后，运行测试脚本：

```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
python3 test/test_supabase_integration.py
```

## 📊 创建的表结构

### 1. users（用户表）
- 存储用户画像、CEFR 等级、强项弱项等

### 2. conversations（对话会话表）
- 存储对话会话信息、状态、摘要等

### 3. messages（消息表）
- 存储对话中的每条消息

### 4. assessments（评估结果表）
- 存储每轮对话的评估结果

### 5. learning_reports（学习报告表）
- 存储生成的学习报告

### 6. audio_files（音频文件表）
- 存储音频文件信息

### 7. user_progress（用户学习进度表）
- 存储用户的学习进度

## ⚠️ 注意事项

1. **网络限制**：由于服务器无法访问 IPv6，无法通过命令行直接连接数据库
2. **权限**：anon key 无法执行 DDL 操作，必须通过 Dashboard 执行
3. **已存在的表**：如果表已存在，`CREATE TABLE IF NOT EXISTS` 会跳过，不会报错

## 🔧 故障排除

### 问题：执行 SQL 时报错 "relation already exists"
**解决**：这是正常的，说明表已经存在，可以继续下一步

### 问题：执行 SQL 时报错 "permission denied"
**解决**：确保使用正确的项目，并且有管理员权限

### 问题：测试脚本报错 "table not found"
**解决**：检查表是否创建成功，运行验证 SQL 查询

## 📝 相关文件

- `scripts/supabase_schema.sql` - SQL 表结构脚本
- `scripts/create_tables_dashboard.py` - 辅助脚本
- `test/test_supabase_integration.py` - 集成测试
- `docs/DATABASE_MIGRATION.md` - 数据库迁移文档

