# 项目结构说明

## 📁 目录结构

```
learning_english/
├── api/                    # API端点
│   ├── main.py            # FastAPI主应用
│   ├── streaming_voice_endpoint.py  # 流式语音对话端点
│   └── ...
│
├── config/                 # 配置管理
│   ├── settings.py        # 应用配置
│   ├── llm_config.py      # LLM配置
│   └── topics.py          # 主题配置
│
├── core/                   # 核心业务逻辑
│   ├── conversation.py    # 对话管理器
│   ├── cefr_mapper.py     # CEFR等级映射
│   └── ...
│
├── models/                 # 数据模型
│   ├── conversation.py    # 对话模型
│   ├── user.py            # 用户模型
│   └── assessment.py      # 评估模型
│
├── services/               # 服务层
│   ├── llm.py             # LLM服务
│   ├── evaluator.py       # 评估服务
│   ├── generator.py        # 问题生成服务
│   ├── quick_evaluator.py # 快速评估服务（LLM prompt）
│   ├── async_evaluator.py # 异步评估服务
│   ├── speech.py          # 语音识别服务
│   ├── tts.py             # 文本转语音服务
│   └── ...
│
├── prompts/                # 提示词管理
│   ├── templates.py       # 提示词模板
│   └── builders.py        # 提示词构建器
│
├── storage/                # 数据存储层
│   └── impl/
│       └── supabase_repository.py  # Supabase实现
│
├── static/                 # 前端静态文件
│   ├── index.html         # 主页面
│   ├── app.js             # 前端JavaScript
│   └── styles.css         # 样式文件
│
├── scripts/                # 脚本文件
│   ├── setup/             # 安装和设置脚本
│   │   ├── install.sh
│   │   ├── setup_venv.sh
│   │   └── ...
│   ├── startup/           # 启动脚本
│   │   └── start.sh
│   ├── check_config.py    # 配置检查工具
│   └── ...                # 数据库脚本等
│
├── test/                   # 测试文件
│   ├── results/           # 测试结果
│   ├── audio/             # 测试音频文件
│   └── ...                # 测试脚本
│
├── docs/                   # 文档
│   ├── features/          # 功能文档
│   │   ├── ASYNC_ASSESSMENT_DESIGN.md
│   │   ├── ASYNC_EVALUATION_IMPLEMENTATION.md
│   │   └── FEATURE_EXPLANATION.md
│   ├── performance/       # 性能文档
│   │   ├── PERFORMANCE_ANALYSIS.md
│   │   ├── PERFORMANCE_OPTIMIZATION.md
│   │   └── ...
│   ├── setup/            # 设置文档
│   └── ...                # 其他文档
│
├── logs/                   # 日志文件
├── test_audio/            # 测试音频目录
├── venv/                   # Python虚拟环境（不提交）
├── README.md              # 项目说明
├── requirements.txt        # Python依赖
└── environment.yml         # Conda环境配置
```

## 📝 文件分类说明

### API层 (`api/`)
- `main.py`: FastAPI应用入口，路由注册
- `streaming_voice_endpoint.py`: WebSocket流式语音对话端点
- 其他端点文件

### 核心业务层 (`core/`)
- `conversation.py`: 对话管理器，处理对话流程
- `cefr_mapper.py`: CEFR等级映射工具

### 服务层 (`services/`)
- `llm.py`: LLM服务抽象和实现
- `evaluator.py`: 完整评估服务（同步）
- `quick_evaluator.py`: 快速评估服务（LLM prompt）
- `async_evaluator.py`: 异步评估服务
- `generator.py`: 问题生成服务
- `speech.py`: 语音识别服务
- `tts.py`: 文本转语音服务

### 数据模型 (`models/`)
- 定义对话、用户、评估等数据模型

### 提示词 (`prompts/`)
- `templates.py`: 各种提示词模板
- `builders.py`: 提示词构建器

### 存储层 (`storage/`)
- 数据持久化抽象和实现（Supabase）

### 前端 (`static/`)
- HTML、CSS、JavaScript前端文件

### 脚本 (`scripts/`)
- `setup/`: 安装和设置脚本
- `startup/`: 启动脚本
- 数据库相关脚本

### 测试 (`test/`)
- `results/`: 测试结果文件
- `audio/`: 测试音频文件
- 各种测试脚本

### 文档 (`docs/`)
- `features/`: 功能文档
- `performance/`: 性能文档
- `setup/`: 设置文档
- 其他技术文档

## 🚀 快速开始

1. **安装依赖**:
   ```bash
   ./scripts/setup/setup_venv.sh
   ```

2. **启动服务**:
   ```bash
   ./scripts/startup/start.sh
   ```

3. **访问前端**:
   ```
   http://localhost:8000/
   ```

## 📚 主要文档

- `README.md`: 项目概述
- `docs/features/FEATURE_EXPLANATION.md`: 功能说明
- `docs/performance/PERFORMANCE_OPTIMIZATION.md`: 性能优化
- `docs/TESTING_GUIDE.md`: 测试指南

