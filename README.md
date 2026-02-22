# LinguaCoach - 智能英语口语对话测评系统

基于提示词工程的动态自适应英语对话测评系统，支持流式语音输入输出。

## 🚀 快速开始

### 安装依赖

```bash
# 使用虚拟环境（推荐）
./scripts/setup/setup_venv.sh

# 或使用Conda
./scripts/setup/setup_conda.sh
```

### 启动服务

```bash
# 启动服务
./scripts/setup/start.sh

# 或启动并测试
./scripts/setup/start_and_test.sh
```

### 访问前端

打开浏览器访问：`http://localhost:8000/`

## 📁 项目结构

```
learning_english/
├── api/                    # API端点
├── config/                 # 配置管理
├── core/                   # 核心业务逻辑
├── docs/                   # 📚 文档
│   ├── features/          # 功能文档
│   ├── performance/       # 性能文档
│   └── ...                # 其他文档
├── models/                 # 数据模型
├── prompts/                # 提示词管理
├── scripts/                # 🔧 脚本
│   └── setup/             # 安装和启动脚本
├── services/               # 服务层
├── static/                 # 前端静态文件
├── storage/                # 数据存储层
├── test/                   # 🧪 测试
│   ├── results/           # 测试结果
│   └── audio/             # 测试音频
└── README.md              # 本文件
```

详细结构说明请查看：`docs/PROJECT_STRUCTURE.md`

## 📚 主要文档

- **项目结构**: `docs/PROJECT_STRUCTURE.md`
- **功能说明**: `docs/features/FEATURE_EXPLANATION.md`
- **性能优化**: `docs/performance/PERFORMANCE_OPTIMIZATION.md`
- **测试指南**: `docs/TESTING_GUIDE.md`
- **整理总结**: `docs/ORGANIZATION_SUMMARY.md`

## 🔧 主要功能

1. **流式语音对话**: WebSocket实时语音输入输出
2. **智能评估**: 快速评估（LLM prompt）+ 完整评估（异步）
3. **动态问题生成**: 基于用户画像、对话历史、兴趣动态生成
4. **实时转录**: 录音过程中实时显示转录结果
5. **性能测试**: 前端性能测试工具

## 🛠️ 技术栈

- **后端**: FastAPI, WebSocket
- **前端**: HTML, CSS, JavaScript
- **LLM**: OpenAI API (通过 yunwu.ai)
- **STT**: FunASR (本地) / Whisper API
- **TTS**: OpenAI TTS
- **存储**: Supabase

## 📝 配置

配置文件：`.env`

主要配置项：
- `LLM_PROVIDER`: LLM提供商（openai）
- `SPEECH_PROVIDER`: 语音识别提供商（funasr/whisper）
- `TTS_PROVIDER`: TTS提供商（openai）
- `STORAGE_BACKEND`: 存储后端（supabase）
- `EVALUATION_CADENCE_TURNS`: 评估节奏（每N轮输出一次评估，默认3）
- `EVALUATION_AGGREGATE_TURNS`: 评估聚合（综合最近N轮，默认3）

## 🧪 测试

```bash
# 前端性能测试
python test/test_frontend_performance.py

# STT性能测试
python test/test_stt_performance.py

# API对比测试
python test/test_api_vs_local.py
```

## 📖 更多信息

查看 `docs/` 目录获取详细文档。
