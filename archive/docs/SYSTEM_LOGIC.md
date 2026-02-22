# 系统逻辑梳理

## 📋 目录

1. [整体架构](#整体架构)
2. [对话流程](#对话流程)
3. [评估流程](#评估流程)
4. [问题生成流程](#问题生成流程)
5. [语音处理流程](#语音处理流程)
6. [数据流](#数据流)

---

## 🏗️ 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     前端 (Frontend)                       │
│  - HTML/CSS/JavaScript                                   │
│  - WebSocket客户端                                       │
│  - MediaRecorder (录音)                                  │
│  - Web Audio API (播放)                                  │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket
                     │
┌────────────────────▼────────────────────────────────────┐
│              API层 (FastAPI)                             │
│  - streaming_voice_endpoint.py                          │
│  - WebSocket端点处理                                     │
│  - 消息路由和分发                                        │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│           核心业务层 (Core)                               │
│  - ConversationManager                                   │
│    ├── start_conversation()                              │
│    ├── process_user_response_quick()                     │
│    └── process_user_response_full()                      │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐      ┌─────────▼──────────┐
│  服务层        │      │   存储层            │
│  - LLM         │      │  - ConversationRepo │
│  - Evaluator   │      │  - UserRepo         │
│  - Generator   │      │  - Supabase         │
│  - STT/TTS     │      └─────────────────────┘
│  - QuickEval   │
│  - AsyncEval   │
└────────────────┘
```

---

## 💬 对话流程

### 1. 开始对话 (`start_conversation`)

```
用户请求开始对话
    ↓
创建Conversation对象
    ↓
获取/创建用户画像 (UserProfile)
    ├── 初始CEFR等级: A1
    ├── 初始分数: 50
    └── 兴趣列表: []
    ↓
构建能力画像 (AbilityProfile)
    ├── cefr_level: 从用户画像获取
    ├── overall_score: 从用户画像获取
    ├── strengths: 从用户画像获取
    └── weaknesses: 从用户画像获取
    ↓
提取用户兴趣 (UserInterests)
    └── 转换为字典格式
    ↓
生成初始问题 (GeneratorService)
    ├── 输入: ability_profile, user_interests
    ├── 使用LLM生成问题
    └── 考虑难度和兴趣匹配
    ↓
保存对话到数据库
    ↓
返回Conversation对象
```

### 2. 处理用户回答 (`process_user_response_quick`)

```
用户回答 (user_response)
    ↓
添加用户消息到对话
    ↓
检测用户是否在问问题
    ├── 如果是问题 → 生成回答
    └── 如果不是 → 继续流程
    ↓
获取对话上下文 (ContextManagerService)
    ├── 最近6条消息
    ├── 对话摘要 (如果有)
    └── 上下文摘要轮次
    ↓
快速评估 (QuickEvaluatorService)
    ├── 输入: user_response, conversation_history, previous_assessment
    ├── 使用LLM prompt快速评估 (<500ms)
    ├── 返回: {
    │     overall_score: float,
    │     cefr_level: str,
    │     strengths: List[str],
    │     weaknesses: List[str],
    │     confidence: float
    │   }
    └── 保存到消息metadata
    ↓
获取用户画像 (UserProfile)
    ├── 从数据库读取
    └── 包含历史兴趣
    ↓
生成下一题 (GeneratorService)
    ├── 输入:
    │   ├── ability_profile (基于快速评估)
    │   ├── conversation_history (最近6条)
    │   ├── previous_topics (已讨论主题)
    │   └── user_interests (用户兴趣)
    ├── 使用LLM生成问题
    └── 考虑难度、历史、兴趣
    ↓
添加助手消息到对话
    ↓
保存对话到数据库
    ↓
返回: (conversation, quick_assessment, next_question)
```

### 3. 完整评估 (`process_user_response_full`)

```
用户回答 (user_response)
    ↓
执行完整评估 (EvaluatorService)
    ├── 输入:
    │   ├── conversation_messages (完整对话历史)
    │   ├── current_response (当前回答)
    │   ├── round_number (轮次)
    │   └── previous_assessments (历史评估)
    ├── 使用LLM进行多维度评估 (2-5秒)
    ├── 评估维度:
    │   ├── 内容相关性 (1-5分)
    │   ├── 语言准确性 (1-5分)
    │   ├── 表达流利度 (1-5分)
    │   ├── 交互深度 (1-5分)
    │   └── 词汇丰富度 (1-5分)
    └── 返回: AssessmentResult
    ↓
更新用户画像 (UserProfile)
    ├── 更新 overall_score
    ├── 更新 cefr_level
    ├── 更新 strengths
    └── 更新 weaknesses
    ↓
提取并更新用户兴趣 (InterestExtractorService)
    ├── 从对话中提取兴趣
    └── 更新用户兴趣列表
    ↓
保存用户画像到数据库
    ↓
更新对话中的评估结果
    ├── 将快速评估替换为完整评估
    └── 保存到消息metadata
    ↓
保存对话到数据库
    ↓
返回: (full_assessment_result, updated_user_profile)
```

---

## 📊 评估流程

### 双评估策略

```
用户回答
    ↓
┌─────────────────────────────────────────┐
│  快速评估 (同步, <500ms)                 │
│  - QuickEvaluatorService                 │
│  - 使用LLM prompt                       │
│  - 立即返回结果                         │
│  - 用于生成下一题                       │
└──────────────┬──────────────────────────┘
               │
               ├──→ 生成下一题 (立即)
               │
               └──→ 启动异步完整评估 (后台)
                    │
                    └──→ 完整评估 (异步, 2-5秒)
                         │
                         ├──→ 更新用户画像
                         ├──→ 更新对话评估结果
                         └──→ 发送完整评估到前端
```

### 快速评估 (`QuickEvaluatorService`)

```python
def quick_evaluate(
    user_response: str,
    conversation_history: List[Dict[str, str]],
    previous_assessment: Dict[str, Any],
    conversation_length: int
) -> Dict[str, Any]:
    """
    快速评估流程:
    1. 构建快速评估prompt
       - 包含用户回答
       - 包含对话历史（最近3轮）
       - 包含上一次评估结果
    2. 调用LLM (temperature=0.3)
    3. 解析JSON响应
    4. 返回评估结果
    """
```

**评估结果格式**:
```json
{
    "overall_score": 75.0,
    "cefr_level": "B1",
    "strengths": ["词汇使用准确", "语法结构清晰"],
    "weaknesses": ["词汇量有限", "复杂句式使用不足"],
    "confidence": 0.8
}
```

### 完整评估 (`EvaluatorService`)

```python
def evaluate(
    conversation_messages: List[Message],
    current_response: str,
    round_number: int,
    previous_assessments: List[Dict[str, Any]]
) -> AssessmentResult:
    """
    完整评估流程:
    1. 构建评估prompt
       - 包含完整对话历史（最近10轮）
       - 包含历史评估记录（最近5次）
       - 包含当前回答
    2. 调用LLM进行多维度评估
    3. 解析评估结果
    4. 返回详细评估结果
    """
```

**评估结果格式**:
```json
{
    "dimension_scores": [
        {"dimension": "内容相关性", "score": 4.0, "comment": "...", "reasoning": "..."},
        {"dimension": "语言准确性", "score": 3.5, "comment": "...", "reasoning": "..."},
        ...
    ],
    "ability_profile": {
        "overall_score": 75.0,
        "cefr_level": "B1",
        "strengths": [...],
        "weaknesses": [...],
        "confidence": 0.85
    }
}
```

---

## ❓ 问题生成流程

### 生成器 (`QuestionGeneratorService`)

```python
def generate_question(
    ability_profile: Dict[str, Any],
    conversation_history: List[Dict[str, str]],
    previous_topics: List[str],
    user_interests: List[Dict[str, Any]]
) -> str:
    """
    问题生成流程:
    1. 获取适配的主题池 (TopicPool)
       - 基于CEFR等级获取可用主题
    2. 构建生成prompt
       - 能力画像 (难度)
       - 对话历史 (连贯性)
       - 已讨论主题 (避免重复)
       - 用户兴趣 (个性化)
    3. 调用LLM生成问题 (temperature=0.7)
    4. 返回生成的问题文本
    """
```

### 生成策略

1. **难度适配**: 基于用户CEFR等级选择合适难度的主题
2. **连贯性**: 考虑对话历史，保持话题连贯
3. **避免重复**: 不重复已讨论的主题
4. **兴趣匹配**: 优先选择用户感兴趣的主题

---

## 🎤 语音处理流程

### WebSocket流式语音对话

```
客户端连接
    ↓
WebSocket握手
    ↓
验证对话存在
    ↓
┌─────────────────────────────────────────┐
│  实时转录 (Realtime Transcription)      │
│  - 客户端每100ms发送音频块              │
│  - 服务端快速STT (FunASR/Whisper)       │
│  - 返回部分转录结果                     │
└──────────────┬──────────────────────────┘
               │
               ↓
用户停止录音
    ↓
发送最终音频
    ↓
完整STT转录
    ↓
处理用户回答
    ├──→ 快速评估
    ├──→ 生成下一题
    └──→ 启动异步完整评估
    ↓
TTS生成语音
    ├──→ 流式发送音频块
    └──→ 客户端播放
```

### 消息流程

**客户端 → 服务端**:
```json
// 开始录音
{"type": "start"}

// 实时音频块
{"type": "audio", "data": "base64_encoded_audio"}

// 停止录音
{"type": "audio_end"}
```

**服务端 → 客户端**:
```json
// 部分转录
{"type": "transcription_partial", "text": "..."}

// 最终转录
{"type": "transcription_final", "text": "..."}

// 快速评估结果
{"type": "assessment", "data": {
    "type": "quick",
    "assessment": {...},
    "user_profile": {...}
}}

// 下一个问题
{"type": "question", "text": "..."}

// TTS音频块
{"type": "audio_chunk", "data": "base64_encoded_audio"}

// 完整评估结果（异步）
{"type": "assessment", "data": {
    "type": "full",
    "assessment": {...},
    "user_profile": {...}
}}
```

---

## 🔄 数据流

### 完整数据流

```
用户录音
    ↓
[前端] MediaRecorder → 音频块 (每100ms)
    ↓
[WebSocket] 发送音频块
    ↓
[后端] STT服务 → 部分转录
    ↓
[WebSocket] 返回部分转录
    ↓
[前端] 显示实时转录
    ↓
用户停止录音
    ↓
[前端] 发送最终音频
    ↓
[后端] STT服务 → 完整转录
    ↓
[后端] ConversationManager.process_user_response_quick()
    ├── 快速评估 (LLM prompt, <500ms)
    ├── 生成下一题 (LLM, 1-2秒)
    └── 启动异步完整评估 (后台)
    ↓
[WebSocket] 发送快速评估结果
[WebSocket] 发送下一个问题文本
    ↓
[后端] TTS服务 → 生成语音 (流式)
    ↓
[WebSocket] 流式发送音频块
    ↓
[前端] Web Audio API → 播放音频
    ↓
[后端] 异步完整评估完成 (2-5秒)
    ├── 更新用户画像
    ├── 更新对话评估结果
    └── 发送完整评估结果
    ↓
[WebSocket] 发送完整评估结果
    ↓
[前端] 更新评估显示
```

### 数据存储

```
Conversation (对话)
├── conversation_id: UUID
├── user_id: str
├── state: ConversationState
├── messages: List[Message]
│   ├── role: MessageRole (USER/ASSISTANT/SYSTEM)
│   ├── content: str
│   └── metadata: Dict
│       └── assessment: Dict (快速/完整评估结果)
├── summary: str (对话摘要)
└── summary_round: int (摘要轮次)

UserProfile (用户画像)
├── user_id: str
├── overall_score: float (0-100)
├── cefr_level: CEFRLevel (A1-C2)
├── strengths: List[str]
├── weaknesses: List[str]
├── interests: List[Interest]
│   ├── category: str
│   ├── weight: float
│   └── tags: List[str]
└── conversation_count: int
```

---

## 🔑 关键设计决策

### 1. 双评估策略

**为什么**:
- 快速评估: 立即生成下一题，提升用户体验
- 完整评估: 后台详细评估，更新用户画像

**实现**:
- 快速评估: LLM prompt (<500ms)
- 完整评估: 多维度LLM评估 (2-5秒，异步)

### 2. 流式处理

**为什么**:
- 实时反馈: 用户看到实时转录
- 低延迟: 流式TTS，边生成边播放

**实现**:
- 音频块: 每100ms发送
- WebSocket: 双向通信
- TTS流式: 边生成边发送

### 3. 上下文管理

**为什么**:
- 连贯性: 保持对话连贯
- 效率: 避免处理过多历史

**实现**:
- 最近6条消息: 用于问题生成
- 对话摘要: 压缩历史信息
- 上下文服务: 统一管理

### 4. 兴趣提取

**为什么**:
- 个性化: 根据兴趣生成问题
- 提升参与度: 用户更感兴趣的话题

**实现**:
- LLM提取: 从对话中提取兴趣
- 权重更新: 动态更新兴趣权重
- 问题生成: 优先匹配兴趣

---

## 📝 总结

### 核心流程

1. **开始对话**: 创建对话 → 获取用户画像 → 生成初始问题
2. **处理回答**: 快速评估 → 生成下一题 → 异步完整评估
3. **更新画像**: 完整评估完成后更新用户画像和兴趣

### 关键特性

- ✅ **快速响应**: 快速评估 + 流式处理
- ✅ **详细评估**: 异步完整评估
- ✅ **个性化**: 基于兴趣和历史的动态问题生成
- ✅ **实时反馈**: 实时转录和流式TTS
- ✅ **数据持久化**: Supabase存储

### 性能优化

- ✅ **模型预热**: FunASR模型预加载
- ✅ **异步处理**: 完整评估异步执行
- ✅ **流式传输**: 音频流式处理
- ✅ **上下文压缩**: 对话摘要减少token





