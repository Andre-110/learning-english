# Conda安装指南

## 情况说明

如果遇到 `conda: command not found`，说明系统未安装Conda。

## 安装选项

### 选项1：安装Miniconda（推荐，轻量级）

Miniconda是Conda的最小安装版本，只包含conda和Python。

#### 自动安装（推荐）

```bash
cd /home/ubuntu/learning_english
./install_conda.sh
```

#### 手动安装

```bash
# 1. 下载Miniconda安装脚本
cd /tmp
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# 2. 运行安装脚本
bash Miniconda3-latest-Linux-x86_64.sh

# 3. 按照提示安装（建议选择默认路径）
# 安装完成后，选择"yes"初始化conda

# 4. 重新加载shell配置
source ~/.bashrc

# 5. 验证安装
conda --version
```

### 选项2：安装Anaconda（完整版）

Anaconda包含更多预装的科学计算包，体积较大。

```bash
# 下载Anaconda
cd /tmp
wget https://repo.anaconda.com/archive/Anaconda3-2023.09-0-Linux-x86_64.sh

# 安装
bash Anaconda3-2023.09-0-Linux-x86_64.sh

# 初始化
source ~/.bashrc
conda --version
```

### 选项3：使用venv（无需安装Conda）

如果不想安装Conda，可以使用Python自带的venv：

```bash
# 使用venv设置脚本
./setup_venv.sh

# 或手动创建
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 安装后设置

### 1. 初始化Conda

```bash
# 对于bash
conda init bash
source ~/.bashrc

# 对于zsh
conda init zsh
source ~/.zshrc
```

### 2. 验证安装

```bash
conda --version
# 应该显示: conda 23.x.x
```

### 3. 创建项目环境

```bash
cd /home/ubuntu/learning_english

# 使用environment.yml创建环境
conda env create -f environment.yml

# 激活环境
conda activate lingua_coach

# 验证环境
python --version
which python
```

## 常见问题

### Q1: 安装后conda命令仍不可用

**解决方案：**

```bash
# 1. 初始化conda
conda init bash  # 或 conda init zsh

# 2. 重新加载shell
source ~/.bashrc  # 或 source ~/.zshrc

# 3. 验证
conda --version
```

### Q2: 权限错误

**解决方案：**

```bash
# 安装到用户目录（推荐）
bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda3

# 或使用sudo（不推荐）
sudo bash Miniconda3-latest-Linux-x86_64.sh
```

### Q3: 下载速度慢

**解决方案：**

使用国内镜像源：

```bash
# 清华大学镜像
wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh

# 或使用conda镜像配置
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --set show_channel_urls yes
```

### Q4: ARM架构（如AWS Graviton）

```bash
# 下载ARM版本
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh
bash Miniconda3-latest-Linux-aarch64.sh
```

## 快速开始（安装Conda后）

```bash
# 1. 创建环境
conda env create -f environment.yml

# 2. 激活环境
conda activate lingua_coach

# 3. 配置API密钥
cp .env.example .env
nano .env  # 填入OPENAI_API_KEY

# 4. 启动服务
uvicorn api.main:app --reload
```

## Conda vs venv 选择建议

| 场景 | 推荐 |
|------|------|
| 已有Conda环境 | 使用Conda |
| 需要管理复杂依赖 | 使用Conda |
| 只需要Python包 | 使用venv |
| 系统资源有限 | 使用venv |
| 团队统一环境 | 使用Conda |

## 卸载Conda（如果需要）

```bash
# 删除conda目录
rm -rf $HOME/miniconda3  # 或 $HOME/anaconda3

# 清理shell配置
# 编辑 ~/.bashrc 或 ~/.zshrc，删除conda相关行
```

## 下一步

安装Conda后：
1. 查看 `docs/CONDA_SETUP.md` - Conda环境设置
2. 运行 `conda env create -f environment.yml` - 创建项目环境
3. 运行 `conda activate lingua_coach` - 激活环境





