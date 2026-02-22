# Conda虚拟环境设置指南

## 前提条件

确保已安装Conda：
- **Miniconda**: https://docs.conda.io/en/latest/miniconda.html
- **Anaconda**: https://www.anaconda.com/products/distribution

检查Conda是否安装：
```bash
conda --version
```

## 方法1：使用设置脚本（推荐）

```bash
cd /home/ubuntu/learning_english
chmod +x setup_conda.sh
./setup_conda.sh
```

## 方法2：使用environment.yml（推荐）

```bash
cd /home/ubuntu/learning_english

# 创建环境（会自动安装所有依赖）
conda env create -f environment.yml

# 激活环境
conda activate lingua_coach

# 配置API密钥
cp .env.example .env
nano .env  # 填入OPENAI_API_KEY

# 启动服务
uvicorn api.main:app --reload
```

## 方法3：手动创建

### 1. 创建Conda环境

```bash
conda create -n lingua_coach python=3.9 -y
```

### 2. 激活环境

```bash
conda activate lingua_coach
```

激活后，命令行提示符会显示 `(lingua_coach)`。

### 3. 安装依赖

```bash
# 升级pip
pip install --upgrade pip

# 安装项目依赖
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
# 创建.env文件
cp .env.example .env

# 编辑.env文件
nano .env
# 填入: OPENAI_API_KEY=your_key_here
```

### 5. 验证安装

```bash
python -c "import fastapi, uvicorn, openai; print('✅ 安装成功')"
```

### 6. 启动服务

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## Conda环境管理

### 激活环境

```bash
conda activate lingua_coach
```

### 退出环境

```bash
conda deactivate
```

### 查看所有环境

```bash
conda env list
```

### 删除环境

```bash
conda env remove -n lingua_coach
```

### 导出环境配置

```bash
conda env export > environment.yml
```

### 更新环境

```bash
conda activate lingua_coach
pip install -r requirements.txt --upgrade
```

## 常见问题

### Q1: Conda未找到命令

**问题：** `conda: command not found`

**解决方案：**

```bash
# 初始化conda（首次使用需要）
conda init bash
# 或
conda init zsh

# 重新加载shell
source ~/.bashrc
# 或
source ~/.zshrc
```

### Q2: 环境已存在

```bash
# 删除旧环境
conda env remove -n lingua_coach

# 重新创建
conda env create -f environment.yml
```

### Q3: 安装依赖失败

确保已激活环境：
```bash
conda activate lingua_coach
pip install -r requirements.txt
```

### Q4: Python版本不匹配

```bash
# 创建指定Python版本的环境
conda create -n lingua_coach python=3.9 -y
```

### Q5: 权限错误

Conda环境安装在用户目录，不需要sudo权限。如果仍有问题：
```bash
conda activate lingua_coach
pip install --user -r requirements.txt
```

## Conda vs venv 对比

| 特性 | Conda | venv |
|------|-------|------|
| 包管理 | conda + pip | pip only |
| 依赖解析 | 更强 | 基础 |
| 非Python包 | 支持 | 不支持 |
| 环境隔离 | 完全隔离 | 完全隔离 |
| 跨平台 | 是 | 是 |
| 大小 | 较大 | 较小 |

## 推荐工作流

### 开发环境

```bash
# 1. 激活环境
conda activate lingua_coach

# 2. 启动服务（开发模式，自动重载）
uvicorn api.main:app --reload

# 3. 在另一个终端测试
python demo_text.py
```

### 生产环境

```bash
# 1. 激活环境
conda activate lingua_coach

# 2. 启动服务（生产模式）
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 环境文件说明

### environment.yml

包含完整的Conda环境配置：
- Python版本
- 所有依赖包
- 通道配置

### requirements.txt

仅包含Python包依赖，用于pip安装。

## 下一步

设置完成后：
1. 查看 `docs/INTERACTION_FLOW.md` - 了解交互流程
2. 查看 `QUICKSTART.md` - 快速开始指南
3. 运行 `python demo_text.py` - 测试系统

## 提示

- **每次使用前**：`conda activate lingua_coach`
- **退出时**：`conda deactivate`
- **更新依赖**：修改`requirements.txt`后运行`pip install -r requirements.txt --upgrade`
- **备份环境**：`conda env export > environment_backup.yml`





