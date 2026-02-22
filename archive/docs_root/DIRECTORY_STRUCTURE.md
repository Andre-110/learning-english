# 项目目录结构说明

本文档说明项目的目录结构，特别是各模块的组织方式。

## 📁 目录结构

```
learning_english/
├── api/                      # API 端点层
│   ├── main.py               # FastAPI 入口
│   ├── auth_endpoint.py      # 认证端点
│   ├── openrouter_audio_endpoint.py   # OpenRouter 音频端点
│   └── streaming_voice_endpoint.py    # 标准流程语音端点
│
├── services/                 # 服务层
│   ├── unified_processor.py  # 【核心】统一处理器
│   ├── openrouter_audio.py   # OpenRouter API 调用
│   ├── llm.py                # 通用 LLM 调用
│   ├── tts.py                # TTS 服务
│   ├── speech.py             # STT 封装
│   ├── funasr_service.py     # FunASR 本地 STT
│   ├── dashscope_audio.py    # DashScope 音频服务
│   ├── qwen_omni_audio.py    # Qwen-Omni 音频服务
│   ├── qwen_omni_tts.py      # Qwen-Omni TTS 服务
│   ├── session_memory.py     # 会话内存管理
│   ├── speech_warmup.py      # STT 预热服务
│   ├── auth.py               # 认证服务
│   └── utils/                # 工具函数
│
├── prompts/                  # 【核心】提示词模板
│   └── templates.py          # 所有 Prompt 集中管理
│
├── models/                   # 数据模型
│   ├── assessment.py         # 评估模型
│   ├── auth.py               # 认证模型
│   ├── conversation.py       # 对话模型
│   └── user.py               # 用户模型
│
├── storage/                  # 存储层
│   ├── repository.py         # 存储接口
│   ├── database_design.md    # 数据库设计文档
│   ├── database_schema.sql   # 数据库 Schema
│   └── impl/                 # 存储实现
│       ├── memory_repository.py    # 内存存储
│       └── supabase_repository.py  # Supabase 存储
│
├── config/                   # 配置管理
│   ├── settings.py           # 应用配置
│   └── llm_config.py         # LLM 配置
│
├── frontend/                 # Vue.js 前端
│   ├── src/                  # 源代码
│   ├── index.html            # 入口 HTML
│   ├── package.json          # 依赖配置
│   └── vite.config.js        # Vite 配置
│
├── tests/                    # 测试脚本
│   ├── audio/                # 测试音频输出
│   ├── test_conversation_*.py    # 对话测试
│   ├── test_qwen_omni_*.py       # Qwen-Omni 测试
│   ├── test_e2e_latency.py       # 端到端延迟测试
│   ├── test_openrouter_*.py      # OpenRouter 测试
│   └── test_streaming_voice.py   # 流式语音测试
│
├── results/                  # 测试结果文件
│   ├── *.json                # JSON 格式测试结果
│   └── *_output.txt          # 文本格式测试输出
│
├── reports/                  # 分析报告
│   ├── conversation_quality_*.md   # 对话质量分析
│   ├── fluency_evaluation_*.md     # 流畅度评估
│   ├── qwen_omni_*.md              # Qwen-Omni 评估
│   ├── process_time_*.md           # 性能分析
│   └── IMPROVEMENT_*.md            # 改进总结
│
├── scripts/                  # 工具脚本
│   ├── compare_vpn_vs_no_vpn.py    # VPN 对比分析
│   ├── extract_suggestions_only.py # 提取建议
│   ├── show_suggestions.py         # 显示建议
│   └── conversation_fluency_evaluator.py  # 流畅度评估器
│
├── docs/                     # 项目文档
│   ├── ARCHITECTURE.md       # 架构文档
│   ├── DATA_FLOW.md          # 数据流文档
│   ├── DIRECTORY_STRUCTURE.md # 目录结构（本文档）
│   ├── QUICKSTART.md         # 快速启动指南
│   └── ...
│
├── logs/                     # 日志文件
│   └── server.log            # 服务器日志
│
├── archive/                  # 归档的废弃代码
│   └── ...                   # 历史代码（不要修改）
│
├── test_audio/               # 测试音频文件
│   └── *.mp3                 # 测试用音频
│
├── requirements.txt          # Python 依赖
├── start.sh                  # 启动脚本
├── start_server.sh           # 服务器启动脚本
└── README.md                 # 项目说明
```

## 📂 核心目录说明

### api/
API 端点层，处理 HTTP 和 WebSocket 请求：
- **main.py**: FastAPI 应用入口，挂载所有路由
- **openrouter_audio_endpoint.py**: OpenRouter 音频流程的 WebSocket 端点
- **streaming_voice_endpoint.py**: 标准语音流程的端点

### services/
服务层，包含所有业务逻辑：
- **unified_processor.py**: 核心处理器，两套流程共用
- **openrouter_audio.py**: OpenRouter API 调用封装
- **tts.py**: 文本转语音服务
- **speech.py**: 语音转文本服务封装

### prompts/
提示词管理，所有 Prompt 集中在这里：
- **templates.py**: 包含系统提示词、用户提示词、初始问题等

### storage/
数据存储层：
- **repository.py**: 存储接口定义
- **impl/memory_repository.py**: 内存存储实现
- **impl/supabase_repository.py**: Supabase 云存储实现

### tests/
测试脚本目录，包含各种测试：
- 对话测试、模型测试、性能测试等

### results/
测试结果文件：
- JSON 格式的结构化测试数据
- TXT 格式的测试输出日志

### reports/
分析报告文档：
- 对话质量分析、性能分析、模型评估等

### archive/
归档的历史代码，**不要修改**：
- 包含已废弃的复杂架构代码

## 🔍 文件命名规范

### 测试文件
- `test_{功能名}.py`: 测试脚本
- `{测试名}_results.json`: 测试结果
- `{测试名}_output.txt`: 测试输出

### 报告文件
- `{主题}_analysis.md`: 分析报告
- `{主题}_summary.md`: 总结报告

## 🔄 更新记录

- 2025-12-23: 目录结构整理优化
  - 合并 test/ 和 tests/ 目录
  - 删除空的 core/ 目录
  - 合并 evaluators/ 到 scripts/
  - 清理根目录临时文件
- 2025-12-17: 初始目录结构整理
