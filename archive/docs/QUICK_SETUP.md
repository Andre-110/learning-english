# 快速设置指南

## 当前状态

- ✅ Python 3.12.3 已安装
- ❌ Conda 未安装
- ❌ pip3 未安装

## 推荐方案：使用venv（最简单）

由于系统已有Python但未安装Conda和pip，推荐使用venv：

### 步骤1：安装pip

```bash
# Ubuntu/Debian系统
sudo apt update
sudo apt install python3-pip python3-venv -y
```

### 步骤2：创建venv环境

```bash
cd /home/ubuntu/learning_english

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
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
# 确保虚拟环境已激活
source venv/bin/activate

# 启动服务
uvicorn api.main:app --reload
```

## 备选方案：安装Conda

如果想使用Conda：

### 步骤1：安装Conda

```bash
# 自动安装Miniconda
./install_conda.sh

# 或手动安装
cd /tmp
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc
```

### 步骤2：创建Conda环境

```bash
conda env create -f environment.yml
conda activate lingua_coach
```

## 一键设置脚本（venv）

如果选择venv，可以运行：

```bash
# 先安装pip和venv
sudo apt update && sudo apt install -y python3-pip python3-venv

# 然后运行设置脚本
./setup_venv.sh
```

## 验证安装

```bash
# 激活环境后
python -c "import fastapi, uvicorn, openai; print('✅ 安装成功')"
```

## 下一步

1. 选择方案（推荐venv）
2. 按照步骤设置
3. 启动服务：`uvicorn api.main:app --reload`
4. 测试：`python demo_text.py`

