# 四轨并行架构 - 完整数据流

## 概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户操作                                        │
│                         按住空格键录音                                        │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           前端 (Vue.js)                                      │
│  conversation.js: startRecording() → stopRecording() → sendAudio()          │
│  WAV 格式, 16kHz, mono                                                       │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ WebSocket 二进制
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    后端 WebSocket 端点                                       │
│              api/openrouter_audio_endpoint.py                               │
│                     audio_chat()                                            │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    process_audio_stream()                                   │
│                       四轨并行处理                                           │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
    ┌───────────────────────────┐   ┌───────────────────────────┐
    │      交互轨 (并行1)        │   │      转录轨 (并行1)        │
    │ ─────────────────────────│   │ ─────────────────────────│
    │ 模型: qwen3-omni-flash   │   │ 模型: FunASR (免费)       │
    │ 输入: 用户音频            │   │ 输入: 用户音频            │
    │ 输出: 英文回复 (流式)     │   │ 输出: 转录文本            │
    │ ─────────────────────────│   │ ─────────────────────────│
    │ WebSocket 消息:          │   │ WebSocket 消息:          │
    │ • text_chunk (流式文字)   │   │ • transcription          │
    │ • sentence_end           │   │                          │
    │ • audio_chunk (TTS)      │   │                          │
    └─────────────┬─────────────┘   └─────────────┬─────────────┘
                  │                               │
                  ▼                               ▼
    ┌───────────────────────────┐   ┌───────────────────────────┐
    │      翻译轨 (并行2)        │   │      评估轨 (并行2)        │
    │ ─────────────────────────│   │ ─────────────────────────│
    │ 模型: qwen-flash (便宜)   │   │ 模型: qwen-flash (便宜)   │
    │ 输入: 英文回复            │   │ 输入: 转录文本            │
    │ 输出: 中文翻译            │   │ 输出: JSON 评估           │
    │ ─────────────────────────│   │ ─────────────────────────│
    │ WebSocket 消息:          │   │ WebSocket 消息:          │
    │ • translation            │   │ • evaluation             │
    └───────────────────────────┘   └───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         数据库更新                                           │
│  ─────────────────────────────────────────────────────────────────────────  │
│  messages 表:                                                               │
│    • 用户消息: transcription + evaluation (metadata)                        │
│    • AI 消息: ai_response + translation (metadata)                          │
│                                                                             │
│  conversations 表 (会话结束时):                                              │
│    • overall_score: 本次会话平均分                                          │
│    • cefr_level: 最终等级                                                   │
│                                                                             │
│  user_profiles 表 (会话结束时):                                             │
│    • overall_score: 历史70% + 本次30% 加权平均                              │
│    • cefr_level: 根据加权分数计算                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 详细数据流

### 1. 用户录音阶段

```
用户按住空格键
    │
    ▼
前端 startRecording()
    │
    ├── 获取麦克风权限 (16kHz, mono)
    ├── 创建 AudioContext
    ├── 收集 PCM 数据到 audioChunks[]
    └── 显示录音状态
    │
    ▼
用户松开空格键
    │
    ▼
前端 stopRecording()
    │
    ├── 将 PCM 转换为 WAV
    ├── 调用 sendAudio(wavBlob)
    └── 显示 "正在处理..."
```

### 2. 音频传输阶段

```
前端 sendAudio()
    │
    ├── ws.send({type: "start"})
    ├── ws.send({type: "audio_meta", format: "wav"})
    ├── ws.send(arrayBuffer)  // 二进制音频
    └── ws.send({type: "audio_end"})
    │
    ▼
后端 audio_chat() 主循环
    │
    ├── 收到 "start" → is_recording = True
    ├── 收到 bytes → audio_buffer.append()
    └── 收到 "audio_end" → 调用 process_audio_stream()
```

### 3. 四轨并行处理阶段

```
process_audio_stream(audio_data)
    │
    │ ══════════════ 第一阶段 (并行) ══════════════
    │
    ├─────────────────────────────────────────────────┐
    │                                                 │
    ▼                                                 ▼
┌─────────────────────┐                 ┌─────────────────────┐
│ run_interaction()   │                 │ run_transcription() │
│                     │                 │                     │
│ processor.interact_ │                 │ stt_service.        │
│   stream()          │                 │   transcribe_audio()│
│                     │                 │                     │
│ 模型: qwen3-omni    │                 │ 模型: FunASR        │
│                     │                 │                     │
│ 流式输出:           │                 │ 输出:               │
│ for chunk in gen:   │                 │ transcription       │
│   ws.send(text_     │                 │                     │
│     chunk)          │                 │ ws.send(            │
│   if sentence_end:  │                 │   transcription)    │
│     ws.send(        │                 │                     │
│       sentence_end) │                 │                     │
│     generate_tts()  │                 │                     │
│     ws.send(        │                 │                     │
│       audio_chunk)  │                 │                     │
└──────────┬──────────┘                 └──────────┬──────────┘
           │                                       │
           │ ai_response                           │ transcription
           │                                       │
    │ ══════════════ 第二阶段 (并行) ══════════════
    │
    ├─────────────────────────────────────────────────┐
    │                                                 │
    ▼                                                 ▼
┌─────────────────────┐                 ┌─────────────────────┐
│ run_translation()   │                 │ run_evaluation()    │
│                     │                 │                     │
│ processor.translate │                 │ processor.evaluate_ │
│   _text()           │                 │   only()            │
│                     │                 │                     │
│ 模型: qwen-flash    │                 │ 模型: qwen-flash    │
│                     │                 │                     │
│ 输出:               │                 │ 输出:               │
│ translation         │                 │ evaluation = {      │
│                     │                 │   overall_score,    │
│ ws.send(            │                 │   cefr_level,       │
│   translation)      │                 │   corrections,      │
│                     │                 │   good_expressions, │
│                     │                 │   encouragement     │
│                     │                 │ }                   │
│                     │                 │                     │
│                     │                 │ ws.send(evaluation) │
└─────────────────────┘                 └─────────────────────┘
```

### 4. 数据库更新阶段

```
保存消息 (每轮结束时)
    │
    ├── messages 表插入用户消息:
    │   {
    │     conversation_id,
    │     sender_role: "user",
    │     content: transcription,
    │     metadata: { evaluation }
    │   }
    │
    └── messages 表插入 AI 消息:
        {
          conversation_id,
          sender_role: "assistant",
          content: ai_response,
          metadata: { translation }
        }

会话结束时 (WebSocket 断开)
    │
    ├── 计算会话平均分:
    │   session_avg_score = sum(session_scores) / len(session_scores)
    │
    ├── 更新 conversations 表:
    │   {
    │     overall_score: session_avg_score,
    │     cefr_level: session_final_level,
    │     state: "completed"
    │   }
    │
    └── 更新 user_profiles 表 (加权平均):
        new_score = old_score * 0.7 + session_avg_score * 0.3
        cefr_level = score_to_cefr(new_score)
```

### 5. 前端展示阶段

```
前端 handleWebSocketMessage()
    │
    ├── text_chunk:
    │   └── 追加到当前 AI 消息 content
    │       assistantMsg.content += data.text
    │       (实时显示打字效果)
    │
    ├── sentence_end:
    │   └── 日志记录
    │
    ├── audio_chunk:
    │   └── queueAudioChunk() → playNextInQueue()
    │       (流式播放 TTS 音频)
    │
    ├── transcription:
    │   └── 更新用户消息 content
    │       userMsg.content = data.text
    │       (显示用户说了什么)
    │
    ├── translation:
    │   └── [待实现] 显示在 AI 消息下方
    │
    ├── evaluation:
    │   └── latestAssessment.value = data.data
    │       userMsg.assessment = data.data
    │       (显示评估卡片: 分数、纠错、好的表达)
    │
    └── done:
        └── isProcessing = false
            latency = data.latency
            (显示延迟统计)
```

## WebSocket 消息时序图

```
时间轴 →

前端                    后端                    模型服务
  │                      │                        │
  │──── start ──────────>│                        │
  │──── audio_meta ─────>│                        │
  │──── [binary] ───────>│                        │
  │──── audio_end ──────>│                        │
  │                      │                        │
  │                      │ ═══ 第一阶段 (并行) ═══│
  │                      │                        │
  │                      │──── 交互轨 ──────────>│ qwen3-omni
  │<─── text_chunk ──────│<─── 流式输出 ─────────│
  │<─── text_chunk ──────│<─── 流式输出 ─────────│
  │<─── sentence_end ────│                        │
  │<─── audio_chunk ─────│<─── TTS ──────────────│ OpenAI TTS
  │<─── text_chunk ──────│<─── 流式输出 ─────────│
  │<─── sentence_end ────│                        │
  │<─── audio_chunk ─────│<─── TTS ──────────────│
  │                      │                        │
  │                      │──── 转录轨 ──────────>│ FunASR (本地)
  │<─── transcription ───│<─── 转录结果 ─────────│
  │                      │                        │
  │                      │ ═══ 第二阶段 (并行) ═══│
  │                      │                        │
  │                      │──── 翻译轨 ──────────>│ qwen-flash
  │<─── translation ─────│<─── 翻译结果 ─────────│
  │                      │                        │
  │                      │──── 评估轨 ──────────>│ qwen-flash
  │<─── evaluation ──────│<─── 评估结果 ─────────│
  │                      │                        │
  │<─── done ────────────│                        │
  │                      │                        │
```

## 模型成本配置

| 轨道 | 模型 | 类型 | 成本 | 用途 |
|------|------|------|------|------|
| 交互轨 | `qwen3-omni-flash` | 音频 | 💰 | 理解语音，生成英文回复 |
| 转录轨 | `FunASR/SenseVoice` | 本地 | ✅ 免费 | 语音转文字 (中英混合) |
| 翻译轨 | `qwen-flash` | 文本 | 💵 便宜 | 英文→中文翻译 |
| 评估轨 | `qwen-flash` | 文本 | 💵 便宜 | 多维度语言评估 |
| TTS | `gpt-4o-mini-tts` | 音频 | 💵 便宜 | 文字转语音 |

## 三层评分系统

```
┌─────────────────────────────────────────────────────────────┐
│                     轮次评分 (Round Score)                   │
│  ─────────────────────────────────────────────────────────  │
│  来源: 评估轨 evaluation.overall_score                       │
│  时机: 每轮对话结束                                          │
│  展示: 评估卡片                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 平均
┌─────────────────────────────────────────────────────────────┐
│                    会话评分 (Session Score)                  │
│  ─────────────────────────────────────────────────────────  │
│  计算: sum(session_scores) / len(session_scores)            │
│  时机: 会话结束 (WebSocket 断开)                             │
│  存储: conversations.overall_score                          │
│  展示: 侧边栏对话列表                                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 加权平均
┌─────────────────────────────────────────────────────────────┐
│                    用户评分 (User Score)                     │
│  ─────────────────────────────────────────────────────────  │
│  计算: old_score * 0.7 + session_score * 0.3                │
│  时机: 会话结束                                              │
│  存储: user_profiles.overall_score                          │
│  展示: 用户头像旁边                                          │
└─────────────────────────────────────────────────────────────┘
```

## 待完善项

1. **前端 translation 展示**: 目前后端发送了 `translation` 消息，但前端 `handleWebSocketMessage` 中没有处理这个消息类型，需要添加展示逻辑。

2. **流式优化**: 当前交互轨是真正的流式，但翻译轨和评估轨是等待完整结果后一次性返回，可以考虑也改为流式。

3. **错误处理**: 某一轨失败时的降级策略。

