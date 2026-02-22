# LinguaCoach 完整流程图

## 系统架构概览

```mermaid
graph TB
    subgraph Frontend["前端 (Vue.js)"]
        VAD[VAD 检测模块<br/>useVAD.js]
        CONV[对话状态管理<br/>conversation.js]
        AUDIO[音频播放器]
    end
    
    subgraph Backend["后端 (FastAPI)"]
        WS[WebSocket 接收器]
        ASR[ASR 转录模块]
        SEM[语义检测模块]
        LLM[LLM 处理模块]
        TTS[TTS 生成模块]
    end
    
    VAD -->|音频帧| WS
    WS -->|消息| CONV
    CONV -->|控制| VAD
    WS --> ASR
    ASR --> SEM
    SEM --> LLM
    LLM --> TTS
    TTS -->|音频数据| WS
    WS -->|音频数据| CONV
    CONV --> AUDIO
```

## 详细流程：用户说话 → AI 回复

```mermaid
sequenceDiagram
    participant User as 用户
    participant VAD as VAD 检测
    participant FE as 前端状态
    participant WS as WebSocket
    participant BE as 后端处理
    participant ASR as ASR 模块
    participant SEM as 语义检测
    participant LLM as LLM 模块
    participant TTS as TTS 模块

    Note over User,TTS: 阶段 1: 用户开始说话
    User->>VAD: 说话
    VAD->>VAD: onSpeechStart()
    VAD->>FE: handleVADSpeechStart()
    
    alt isAISpeaking == true
        FE-->>VAD: return false
        VAD->>VAD: isRecordingSessionValid = false
        Note over VAD: 忽略，不录音
    else isAISpeaking == false
        FE->>FE: 检查 waitingForMore
        alt 有 waitingForMore 消息
            FE->>FE: 复用旧消息
            FE->>FE: waitingForMore = false
        else 没有 waitingForMore
            FE->>FE: 创建新消息
        end
        FE->>WS: {type: 'start'}
        FE-->>VAD: return true
        VAD->>VAD: isRecordingSessionValid = true
        VAD->>VAD: isSpeaking = true
    end

    Note over User,TTS: 阶段 2: 实时发送音频
    loop 每帧音频
        VAD->>VAD: onFrameProcessed()
        alt isSpeaking && isRecordingSessionValid && !isAISpeaking
            VAD->>WS: 音频帧 (binary)
            WS->>BE: 累积到 streaming_audio_frames
        end
    end

    Note over User,TTS: 阶段 3: 用户停止说话
    User->>VAD: 静默 1500ms
    VAD->>VAD: onSpeechEnd()
    alt isRecordingSessionValid == true
        VAD->>FE: handleVADSpeechEnd()
        FE->>WS: {type: 'stop_audio'}
        VAD->>VAD: isRecordingSessionValid = false
        VAD->>VAD: isSpeaking = false
    else isRecordingSessionValid == false
        Note over VAD: 忽略，不发送 stop_audio
    end

    Note over User,TTS: 阶段 4: ASR 转录
    BE->>BE: 收到 stop_audio
    BE->>ASR: pipeline.transcribe(wav_audio)
    ASR-->>BE: transcription

    Note over User,TTS: 阶段 5: 语义检测
    BE->>SEM: check_async(transcription)
    SEM-->>BE: (is_complete, confidence, reason)

    alt 语义不完整 (TENTATIVE)
        BE->>BE: accumulated_transcript += transcription
        BE->>FE: {type: 'waiting_for_more', text, tts_delay: 5.0}
        FE->>FE: waitingForMore = true
        FE->>FE: isProcessing = false
        BE->>BE: 启动后台任务 (延迟 5s)
        
        Note over BE: 等待 5 秒
        loop 检查用户是否继续说话
            alt 收到 start 信号
                BE->>BE: user_speaking_again = true
                BE->>BE: 取消 tentative_task
                Note over BE: 退出等待，回到阶段 1
            else 5 秒超时
                BE->>BE: 触发 FINAL 处理
            end
        end
    else 语义完整 (FINAL)
        BE->>BE: 立即触发 LLM
    end

    Note over User,TTS: 阶段 6: LLM 处理
    BE->>LLM: process_text(transcription)
    BE->>FE: {type: 'processing', stage: 'llm'}
    FE->>FE: isProcessing = true
    LLM-->>BE: 流式文本响应
    BE->>FE: {type: 'response', text: chunk}
    FE->>FE: 更新 AI 消息内容

    Note over User,TTS: 阶段 7: TTS 生成
    BE->>TTS: synthesize(text)
    TTS-->>BE: 音频数据 (PCM)
    BE->>FE: {type: 'audio_chunk', data: base64}
    FE->>FE: setAISpeaking(true)
    FE->>AUDIO: queueAudioChunk()
    AUDIO->>AUDIO: 播放音频

    Note over User,TTS: 阶段 8: 音频播放完毕
    BE->>FE: {type: 'audio_end'}
    FE->>FE: scheduleAISpeakingOff()
    AUDIO->>AUDIO: 最后一个 PCM onended
    AUDIO->>FE: onLastAudioChunkEnded()
    FE->>FE: setAISpeaking(false)
    BE->>FE: {type: 'done'}
    FE->>FE: isProcessing = false
```

## 关键状态变量

### 前端状态变量 (conversation.js)

| 变量 | 类型 | 作用 | 设置时机 |
|------|------|------|----------|
| `isAISpeaking` | `ref<boolean>` | AI 是否正在说话 | `audio_chunk` → true<br/>`onLastAudioChunkEnded()` → false |
| `isProcessing` | `ref<boolean>` | 后端是否正在处理 | `processing: llm` → true<br/>`done` / `error` → false<br/>`waiting_for_more` → false |
| `isSpeaking` | `ref<boolean>` | 用户是否正在说话 | VAD `onSpeechStart` → true<br/>VAD `onSpeechEnd` → false |
| `isRecording` | `ref<boolean>` | 是否正在录音 | `recording_started` → true<br/>`transcription` → false |
| `waitingForMore` | `message.waitingForMore` | 消息是否等待继续 | `waiting_for_more` → true<br/>用户继续说话 → false |
| `isRecordingSessionValid` | `let boolean` | 当前录音会话是否有效 | `onSpeechStart` 回调返回 true → true<br/>`onSpeechEnd` → false |

### 后端状态变量 (pipeline_context)

| 变量 | 类型 | 作用 | 设置时机 |
|------|------|------|----------|
| `llm_status` | `str` | LLM 处理状态 | `TENTATIVE` / `FINAL` / `IDLE` |
| `is_processing` | `bool` | 是否正在处理 | LLM 开始 → true<br/>LLM 结束 → false |
| `accumulated_transcript` | `str` | 累积的转录文本 | TENTATIVE 模式累积 |
| `user_speaking_again` | `bool` | 用户是否继续说话 | `start` 消息 → true<br/>`stop_audio` → false |
| `tentative_task` | `asyncio.Task` | TENTATIVE 等待任务 | TENTATIVE 模式创建<br/>`start` 消息取消 |

## 关键决策点

### 决策点 1: VAD 是否开始录音

```mermaid
graph TD
    A[VAD 检测到说话] --> B{isAISpeaking?}
    B -->|true| C[return false<br/>不录音]
    B -->|false| D[调用 handleVADSpeechStart]
    D --> E{回调返回?}
    E -->|false| C
    E -->|true| F[isRecordingSessionValid = true<br/>开始录音]
```

### 决策点 2: 语义完整性判断

```mermaid
graph TD
    A[ASR 完成] --> B[语义检测]
    B --> C{is_complete && confidence >= 0.7?}
    C -->|否| D[TENTATIVE 模式]
    C -->|是| E[FINAL 模式]
    D --> F[发送 waiting_for_more]
    D --> G[启动 5s 延迟任务]
    E --> H[立即触发 LLM]
```

### 决策点 3: TENTATIVE 等待期间

```mermaid
graph TD
    A[TENTATIVE 等待 5s] --> B{收到 start 信号?}
    B -->|是| C[取消 tentative_task]
    B -->|否| D{5s 超时?}
    C --> E[用户继续说话流程]
    D -->|是| F[触发 FINAL LLM]
    D -->|否| A
```

### 决策点 4: 用户继续说话时的消息复用

```mermaid
graph TD
    A[用户开始说话] --> B{有 waitingForMore 消息?}
    B -->|是| C[复用旧消息<br/>waitingForMore = false]
    B -->|否| D[创建新消息]
    C --> E[发送 start]
    D --> E
```

## 音频播放时序

```mermaid
sequenceDiagram
    participant BE as 后端
    participant FE as 前端
    participant AUDIO as 音频播放器

    BE->>FE: audio_chunk (PCM 片段 1)
    FE->>FE: setAISpeaking(true)
    FE->>AUDIO: queueAudioChunk()
    AUDIO->>AUDIO: source1.start(startTime)
    AUDIO->>AUDIO: nextPlayTime = startTime + duration1

    BE->>FE: audio_chunk (PCM 片段 2)
    FE->>AUDIO: queueAudioChunk()
    AUDIO->>AUDIO: source2.start(nextPlayTime)
    AUDIO->>AUDIO: nextPlayTime += duration2

    BE->>FE: audio_end
    FE->>FE: audioStreamEnded = true
    FE->>FE: lastAudioSource = sourceN

    AUDIO->>AUDIO: sourceN.onended()
    AUDIO->>FE: onLastAudioChunkEnded()
    FE->>FE: setTimeout(300ms)
    FE->>FE: setAISpeaking(false)
```

## 错误处理流程

```mermaid
graph TD
    A[处理中] --> B{发生错误?}
    B -->|是| C[发送 error 消息]
    C --> D[前端收到 error]
    D --> E[isProcessing = false]
    D --> F[清理状态]
    B -->|否| G[正常完成]
    G --> H[发送 done 消息]
    H --> E
```

## 打断机制

```mermaid
sequenceDiagram
    participant User as 用户
    participant FE as 前端
    participant BE as 后端
    participant LLM as LLM 处理

    Note over BE,LLM: AI 正在说话或处理中
    User->>FE: 开始说话
    FE->>FE: handleVADSpeechStart()
    FE->>BE: {type: 'start'}
    
    alt is_processing == true
        BE->>BE: llm_cancelled = true
        BE->>BE: tentative_task.cancel()
        BE->>LLM: 检查 cancel_token
        LLM-->>BE: 停止处理
    end
    
    alt is_speaking == true
        BE->>BE: interrupt_event.set()
        BE->>FE: {type: 'interrupt'}
        FE->>FE: stopAllAudio()
        FE->>FE: setAISpeaking(false)
    end
    
    BE->>BE: 开始新的录音流程
```


