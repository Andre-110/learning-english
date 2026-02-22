# 快速设置指南

## 当前状态

系统检测到 `uvicorn` 和 `pip3` 未安装。请按照以下步骤设置：

## 方法1：使用安装脚本（推荐）

```bash
cd /home/ubuntu/learning_english
./install.sh
```

这个脚本会：
1. 检查Python版本
2. 安装pip（如果需要）
3. 安装所有依赖
4. 创建.env文件

## 方法2：手动安装

### 步骤1：安装pip

```bash
sudo apt update
sudo apt install python3-pip
```

### 步骤2：安装依赖

```bash
cd /home/ubuntu/learning_english
pip3 install -r requirements.txt --user
```

### 步骤3：配置API密钥

```bash
# 创建.env文件
cp .env.example .env

# 编辑.env文件
nano .env
# 填入: OPENAI_API_KEY=your_key_here
```

### 步骤4：启动服务

```bash
# 使用uvicorn
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 或使用Python
python3 api/main.py
```

## 验证安装

运行以下命令验证：

```bash
python3 -c "import fastapi, uvicorn, openai; print('✅ 依赖安装成功')"
```

## 如果遇到问题

1. **权限错误**：使用 `--user` 参数或虚拟环境
2. **模块未找到**：确保在项目根目录
3. **API密钥错误**：检查.env文件

详细说明请查看 `INSTALL.md`

