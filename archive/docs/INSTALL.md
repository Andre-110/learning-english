# 安装指南

## 系统要求

- Python 3.9+
- pip（Python包管理器）

## 安装步骤

### 步骤1：安装pip（如果未安装）

```bash
# Ubuntu/Debian系统
sudo apt update
sudo apt install python3-pip

# 或者使用get-pip.py
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py --user
```

### 步骤2：安装项目依赖

```bash
cd /home/ubuntu/learning_english
pip3 install -r requirements.txt --user
```

如果使用虚拟环境（推荐）：

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 步骤3：配置环境变量

```bash
# 创建.env文件
cp .env.example .env

# 编辑.env文件，填入API密钥
nano .env
# 或
vim .env
```

### 步骤4：验证安装

```bash
# 检查Python版本
python3 --version

# 检查pip版本
pip3 --version

# 检查依赖是否安装
python3 -c "import fastapi, uvicorn, openai; print('依赖安装成功')"
```

### 步骤5：启动服务

```bash
# 方式1：使用uvicorn
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 方式2：使用Python
python3 api/main.py

# 方式3：使用启动脚本
chmod +x start.sh
./start.sh
```

## 常见问题

### Q1: pip未找到
```bash
# 安装pip
sudo apt install python3-pip
```

### Q2: 权限错误
```bash
# 使用--user参数
pip3 install -r requirements.txt --user

# 或使用虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Q3: 模块导入错误
```bash
# 确保在项目根目录
cd /home/ubuntu/learning_english

# 检查Python路径
python3 -c "import sys; print(sys.path)"
```

### Q4: API密钥错误
确保`.env`文件存在且包含有效的API密钥：
```bash
OPENAI_API_KEY=your_key_here
```

## 快速安装脚本

运行以下命令一键安装：

```bash
# 安装pip（如果需要）
sudo apt update && sudo apt install -y python3-pip

# 安装依赖
pip3 install -r requirements.txt --user

# 创建.env文件（如果不存在）
if [ ! -f .env ]; then
    cp .env.example .env
    echo "请编辑.env文件，填入API密钥"
fi
```

