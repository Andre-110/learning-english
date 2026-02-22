# 环境变量配置指南

## .env文件已创建

`.env`文件已经创建，现在需要填入你的API密钥。

## 编辑.env文件

### 方法1：使用nano（推荐新手）

```bash
nano .env
```

编辑内容：
- 找到 `OPENAI_API_KEY=your_openai_api_key_here`
- 替换为你的实际API密钥：`OPENAI_API_KEY=sk-...`

保存：按 `Ctrl+X`，然后 `Y`，然后 `Enter`

### 方法2：使用vim

```bash
vim .env
```

- 按 `i` 进入编辑模式
- 修改 `OPENAI_API_KEY` 的值
- 按 `Esc` 退出编辑模式
- 输入 `:wq` 保存并退出

### 方法3：直接使用sed命令（快速）

```bash
# 替换API密钥（将YOUR_API_KEY替换为实际密钥）
sed -i 's/your_openai_api_key_here/YOUR_ACTUAL_API_KEY/g' .env
```

## .env文件内容说明

```bash
# LLM配置
OPENAI_API_KEY=your_openai_api_key_here    # 必须：你的OpenAI API密钥
ANTHROPIC_API_KEY=your_anthropic_api_key_here  # 可选：Anthropic API密钥

# 模型选择
PRIMARY_LLM_MODEL=gpt-4                    # 主要模型（用于评估和生成）
SECONDARY_LLM_MODEL=gpt-3.5-turbo          # 辅助模型（用于摘要等）

# LLM提供商
LLM_PROVIDER=openai                        # openai 或 anthropic

# 系统配置
MAX_CONVERSATION_ROUNDS=20                  # 最大对话轮数
CONTEXT_SUMMARY_INTERVAL=5                 # 每5轮生成摘要
LOG_LEVEL=INFO                             # 日志级别

# 存储配置
STORAGE_BACKEND=memory                      # 存储后端（memory/database/redis）
```

## 获取OpenAI API密钥

1. 访问 https://platform.openai.com/api-keys
2. 登录你的OpenAI账户
3. 点击 "Create new secret key"
4. 复制生成的密钥
5. 粘贴到 `.env` 文件中

## 验证配置

配置完成后，验证：

```bash
# 检查.env文件内容
cat .env | grep OPENAI_API_KEY

# 运行配置检查脚本
python scripts/check_config.py
```

## 安全提示

⚠️ **重要：**
- `.env` 文件包含敏感信息，不要提交到Git
- `.env` 已在 `.gitignore` 中，不会被版本控制
- 不要分享你的API密钥给他人

## 下一步

配置好API密钥后：

```bash
# 1. 确保虚拟环境已激活
source venv/bin/activate

# 2. 安装依赖（如果还没安装）
pip install -r requirements.txt

# 3. 启动服务
uvicorn api.main:app --reload
```

## 常见问题

### Q1: 如何查看.env文件？

```bash
cat .env
```

### Q2: 如何重新创建.env文件？

```bash
./setup_env.sh
```

### Q3: API密钥格式是什么？

OpenAI API密钥格式：`sk-...`（以sk-开头）

### Q4: 可以使用Anthropic吗？

可以，修改 `.env` 文件：
```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_key_here
```

