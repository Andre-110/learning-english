# 虚拟环境设置指南

## 快速设置

运行一键设置脚本：

```bash
cd /home/ubuntu/learning_english
./setup_venv.sh
```

## 手动设置步骤

### 1. 创建虚拟环境

```bash
cd /home/ubuntu/learning_english
python3 -m venv venv
```

### 2. 激活虚拟环境

```bash
source venv/bin/activate
```

激活后，命令行提示符会显示 `(venv)`。

### 3. 升级pip

```bash
pip install --upgrade pip
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 配置环境变量

```bash
# 创建.env文件
cp .env.example .env

# 编辑.env文件
nano .env
# 填入: OPENAI_API_KEY=your_key_here
```

### 6. 验证安装

```bash
python -c "import fastapi, uvicorn, openai; print('✅ 安装成功')"
```

### 7. 启动服务

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## 使用虚拟环境

### 激活虚拟环境

每次使用前需要激活：

```bash
source venv/bin/activate
```

### 退出虚拟环境

```bash
deactivate
```

### 检查是否在虚拟环境中

```bash
which python
# 应该显示: /home/ubuntu/learning_english/venv/bin/python
```

## 常见问题

### Q1: 虚拟环境已存在怎么办？

```bash
# 删除旧环境
rm -rf venv

# 重新创建
python3 -m venv venv
```

### Q2: 找不到venv模块？

```bash
sudo apt update
sudo apt install python3-venv
```

### Q3: 安装依赖失败？

确保已激活虚拟环境：
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Q4: 权限错误？

使用虚拟环境不需要sudo权限，如果仍有问题：
```bash
pip install --user -r requirements.txt
```

## 虚拟环境优势

1. **隔离依赖**：不影响系统Python环境
2. **版本控制**：可以锁定依赖版本
3. **易于清理**：删除venv文件夹即可
4. **多项目支持**：不同项目可以使用不同版本

## 下一步

设置完成后，查看：
- `docs/INTERACTION_FLOW.md` - 了解交互流程
- `QUICKSTART.md` - 快速开始指南





