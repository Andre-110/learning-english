# 环境设置指南

本项目支持两种虚拟环境方式：

## 方式1：Conda（推荐）

### 前提：安装Conda

如果遇到 `conda: command not found`，请先安装Conda：

```bash
# 自动安装（推荐）
./install_conda.sh

# 或查看安装指南
cat docs/CONDA_INSTALL.md
```

### 快速设置

```bash
# 使用environment.yml（推荐）
conda env create -f environment.yml
conda activate lingua_coach

# 或使用设置脚本
./setup_conda.sh
```

### 详细说明

- `docs/CONDA_INSTALL.md` - Conda安装指南
- `docs/CONDA_SETUP.md` - Conda环境设置

## 方式2：venv（Python标准）

### 快速设置

```bash
# 使用设置脚本
./setup_venv.sh

# 或手动创建
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 详细说明

查看 `docs/VENV_SETUP.md`

## 选择建议

- **使用Conda**：如果你已经安装了Anaconda/Miniconda，或者需要管理复杂的依赖
- **使用venv**：如果你只需要Python包管理，或者系统资源有限

## 通用步骤

无论使用哪种方式，都需要：

1. **创建并激活环境**
2. **安装依赖**：`pip install -r requirements.txt`
3. **配置API密钥**：编辑`.env`文件
4. **启动服务**：`uvicorn api.main:app --reload`

## 验证安装

```bash
python -c "import fastapi, uvicorn, openai; print('✅ 安装成功')"
```

