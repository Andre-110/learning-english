# ASR 录入不完整问题 — 原因分析

> 基于当前代码与日志的结论，用于指导修复「语音转文字不完整、只录到开头/1～2 个词」的反馈。

---

## 一、现象回顾

- **王雅蓉**：录入不进去、录入不完整，破坏沉浸感  
- **wyx**：只能录入最开始的回答，个别只识别 1～2 个词  
- **朱音**：一大半没有顺利转出来  

共性：**流式 ASR 经常只返回「前半句」或极少量词，而不是整段话。**

---

## 二、根因分析（按可能性排序）

### 1. 未在取结果前发送「结束流」给豆包 ASR（最可能）

**结论：后端在取转录结果之前，没有先向豆包发送「结束流」信号（EOS / `is_last=True`），导致拿到的是流式过程中的中间结果，而不是整句最终结果。**

**依据：**

- 豆包 ASR 使用流式协议，支持「最后一个音频包带 `is_last=True`」表示用户说完，服务端才会给出**最终**结果。
- 当前逻辑（`api/gpt4o_pipeline_endpoint.py`）在收到前端的 `stop_audio` 后：
  1. 等待 ASR `is_processing` 结束（最多约 1 秒）
  2. **直接**调用 `asr.get_full_transcript()` 取当前内存里的转录
  3. 只有在「语义完整并决定触发 LLM」之后，才调用 `await deepgram_context["asr"].stop_stream()`  
     → `stop_stream()` 里才会发送「空音频 + `is_last=True`」给豆包并关连接

也就是说：**取 transcript 时，豆包从未收到「我说完了」的信号**，一直处于「流式进行中」，返回的多数是增量/中间结果（如 "Oh" → "Oh, hello"），而不是整段话的 final 结果。

日志也能佐证：出现 `[Doubao ASR] 转录: 'Oh....' (final=False)`、`'Oh, hello....' (final=False)`，说明拿到的就是非 final 的中间文本。

**影响：**  
用户说了一整句，但后端只用「当前流式快照」作为最终录入，表现为：只录到开头几个词、或 1～2 个词。

---

### 2. 前端 VAD 静默判定过短，导致「句中被截断」

**结论：** 静默满 **1 秒**就判定「说完了」并发 `stop_audio`，用户句中停顿稍长（如思考、换气）就会被提前截断，只保留前半句。

**依据：**

- `frontend/src/composables/useVAD.js` 中：
  - `redemptionMs: 1000` → 连续 1 秒静默即触发 `onSpeechEnd`
  - `onSpeechEnd` 里会触发 `stop_audio`（或等价逻辑）
- 后端以 `stop_audio` 为「用户说完」的主入口，一旦收到就按「当前 ASR 结果」做后续处理。

若用户说「I think… [停顿 1s] …we should go」，在 1 秒处就会结束，ASR 只处理到「I think」，后半句不会进入同一段流，表现为「只录到开头」。

**影响：**  
句中停顿 ≥1s 的句子容易被截成「前半句」，和「只录到 1～2 个词」的反馈一致。

---

### 3. 豆包 8 秒超时导致长句被截断

**结论：** 豆包侧存在约 **8 秒** 无数据/无活动的超时（如 error_code 45000081），超时后会断连并可能触发重连；若用户单次说话超过 8 秒，后半段可能丢失或只保留超时前的部分结果。

**依据：**

- `services/doubao_asr.py` 中有对 45000081 的处理：断连、保存当前 `_full_transcript`、触发重连。
- 长句或边说边想时，单次流很容易超过 8 秒，此时后端拿到的 `get_full_transcript()` 只能是「超时前」的片段。

**影响：**  
长句或慢速说话时，容易出现「一大半没转出来」或只看到前半句。

---

### 4. 流式音频与 stop_audio 的时序（次要）

**结论：** 理论上存在「最后一小段音频尚未全部写入 ASR 就收到 stop_audio」的边界情况，但当前实现是边说边发、`stop_audio` 在静默 1s 后发，通常最后未发送的只是静默段，对「整句内容」影响小于上述 1～3。  
若未来调整 VAD 或网络抖动变大，这里可能放大为「尾巴几个字丢失」。

---

## 三、与「只录到开头/1～2 个词」的对应关系

| 现象 | 最可能原因 |
|------|------------|
| 只录到开头几个词 / 1～2 个词 | **原因 1**：未先发 EOS 就取 transcript，拿到的是流式中间结果 |
| 句中停顿后后半句没了 | **原因 2**：VAD 1 秒静默就结束，句中停顿被当成「说完了」 |
| 长句一大半没转出来 | **原因 1 + 原因 3**：既没 EOS 又可能遇到 8 秒超时 |
| 偶尔完全录不进去 | 网络/连接问题、或 8 秒超时后重连导致当次结果被清空/未合并 |

---

## 四、修复建议（优先级）

### P0：在取转录前对豆包发送「结束流」

- 在 `stop_audio` 分支中，**在**调用 `get_full_transcript()` **之前**：
  - 先对当前豆包 ASR 连接调用一次「结束流」：
    - 要么：对豆包发送「最后一包音频 + `is_last=True`」（若协议支持）
    - 要么：直接调用现有 `stop_stream()` 中「发送空包 + `is_last=True`」的逻辑（不一定要立刻关连接，视豆包 API 是否要求关连接而定）
  - 再等待 300～500ms 让豆包返回最终结果
  - 然后再 `get_full_transcript()` 并继续后续语义判断与 LLM
- 这样流式 ASR 会输出「整句 final」，而不是当前中间快照。

### P1：适当拉长前端 VAD 静默判定

- 将 `redemptionMs` 从 1000 提高到 **1500～2000 ms**，或做成可配置（例如按环境/用户设置）。
- 可同时保留「长静默后自动结束」的兜底，避免长时间不结束。

### P2：豆包长句与超时

- 与豆包侧确认：8 秒超时是否可调、或是否有「仅延长活动超时」的配置。
- 若单次说话经常超过 8 秒，可考虑：
  - 在 8 秒前主动发一次「中间 EOS」再起新流（若豆包支持），或
  - 在超时重连后，把「保存的转录」与重连后的新结果做合并展示（若产品上接受分段结果）。

---

## 五、搜索验证（代码位置）

### 5.1 当前错误用法：先取 transcript 再关流

**`api/gpt4o_pipeline_endpoint.py`（stop_audio 分支）：**

- 约 **1645 行**：`deepgram_transcription = asr.get_full_transcript()` ← 直接读内存，**未先发 EOS**
- 约 **1876 / 1949 / 2003 行**：`await deepgram_context["asr"].stop_stream()` ← 在语义完整/空转录等分支里**之后**才关流

即：**先 `get_full_transcript()`，后 `stop_stream()`**，豆包从未在「取结果前」收到 `is_last=True`。

### 5.2 豆包侧：EOS 与返回值

**`services/doubao_asr.py`：**

- **525–571 行** `stop_stream()`：发送 `_build_audio_request(..., is_last=True)`（空包），等 0.5s，关连接，**返回** `self._full_transcript`
- **842–844 行** `get_full_transcript()`：仅 `return self._full_transcript`，**不发送任何包**

结论：要拿「发完 EOS 后的最终结果」，应走 **`await asr.stop_stream()`**，而不是 `get_full_transcript()`。

### 5.3 其他模块的正确用法（对比）

| 位置 | 做法 |
|------|------|
| `api/openrouter_audio_endpoint.py` 约 1837 行 | `transcript = await asr.stop_stream()` ✅ 用关流拿结果 |
| `services/gpt4o_pipeline.py` 约 446 行（批量 ASR） | 发完音频后 `final_result = await asr.stop_stream()` ✅ |
| `tests/test_doubao_asr_e2e.py` 等 | 均用 `await asr.stop_stream()` 取最终转录 ✅ |

只有 **gpt4o_pipeline_endpoint 的 stop_audio 分支** 用了「只读 get_full_transcript、后置 stop_stream」，与根因一致。

### 5.4 P0 修复要点

在 **stop_audio** 分支里，当 ASR 已连接且为豆包（或需 EOS 的 ASR）时：

- **改为**：`deepgram_transcription = await asr.stop_stream()`（先发 EOS、等结果、关连接，返回值即最终转录）
- **注意**：`stop_stream()` 会关闭当前连接，后续同一分支里不再对同一 asr 调用 `stop_stream()`（1876/1949/2003 等处需判断「已通过 stop_stream 取过结果则跳过」）

---

## 六、网络上可参考的解决办法

### 6.1 流式 ASR「先结束流再取最终结果」（通用）

**Deepgram、AssemblyAI 等文档一致建议：**

1. **停止向流式连接发送音频**
2. **发送显式的「结束/定型」消息**  
   - Deepgram：发送 `Finalize`，再收 `Results`（含完整 transcript）  
   - AssemblyAI：等待 "End of utterance (Final transcript)" 再关  
3. **收到最终转录后再关闭连接**  
   - Deepgram：收到最终结果后再发 `CloseStream`  

若在未 Finalize 或未等到 End of utterance 时就关连接或读结果，容易只拿到**部分/中间结果**，与当前现象一致。  
→ 对应本项目的 **P0**：先发 EOS（豆包用 `is_last=True`），等 300～500ms 再取 transcript 或直接用 `stop_stream()` 返回值。

**参考：**  
- [Deepgram – Finalize](https://developers.deepgram.com/docs/finalize)  
- [Deepgram – Close Stream](https://developers.deepgram.com/docs/close-stream)  
- [AssemblyAI – Streaming message sequence](https://www.assemblyai.com/docs/speech-to-text/universal-streaming/message-sequence)

---

### 6.2 豆包/火山引擎流式识别与 `is_last`

火山引擎豆包语音文档说明：

- 流式识别响应里带 **`is_last`** 字段；**当 `is_last` 为真时表示识别已完成，此时返回的才是最终结果**。
- 流式过程中会持续返回中间结果，只有收到带 `is_last=true` 的响应后，文本才是最终确认的。

因此客户端必须在**发送完音频并发出「结束」信号**（如最后一包带结束标识）后，**等待服务端返回带 `is_last` 的最终结果**，再使用该文本。当前实现若从未发结束包就取 transcript，拿到的就是中间结果。  
→ 与本文「先 `stop_stream()`（内部发 is_last）再取结果」的 P0 修复一致。

**参考：**  
- [豆包语音 - 识别结果](https://www.volcengine.com/docs/6561/120559)  
- [豆包语音 - 流式语音识别](https://www.volcengine.com/docs/6561/80818)

---

### 6.3 实时 ASR「只识别出前几个词」的常见原因与对策

- **原因**：未在结束前做「定型/结束流」就取结果，或延迟过短导致模型未输出完整句。  
- **对策**：  
  - 适当增加**结束前的等待/延迟**（如 Speechmatics 的 `max_delay` 约 0.7～2s），在保证实时感的前提下让模型输出更完整。  
  - 使用**部分结果 + 最终结果**：先展示 partial，再在收到 final 后替换，避免用户只看到「前半句」。  
- **长句/长音频**：结合 VAD 与分段，避免整段超长导致超时或只出前半段。

→ 对应本项目：P0 发 EOS 并等 0.3～0.5s 再取结果；P2 关注豆包 8 秒超时与长句分段。

---

### 6.4 VAD 静默时长（redemption）建议

- **Silero VAD**：常见默认 **1400 ms（1.4 秒）** 作为「静默多久算说完」。  
- **Vivox 等**：有使用 **2000 ms（2 秒）** 作为「挂起」静默。  
- **折中**：  
  - 要更快响应：300～400 ms（易误截断）。  
  - 要少误截断、允许句中停顿：**1400～2000 ms** 更稳妥。

当前项目为 **1000 ms**，略短于常见默认，句中停顿 ≥1s 易被当成「说完了」。  
→ 对应 **P1**：将 `redemptionMs` 提到 **1500～2000 ms**，可减少「只录到前半句」的体感。

**参考：**  
- [@ricky0123/vad – Algorithm](https://docs.vad.ricky0123.com/user-guide/algorithm)  
- Vivox VAD parameter specifics（vad_hangover 约 2s）

---

## 七、小结

- **ASR 录入不完整** 的主要技术原因是：**未在读取结果前向豆包发送结束流（EOS）**，导致使用的是流式中间结果而非整句最终结果；叠加 **VAD 1 秒静默即结束** 和 **豆包 8 秒超时**，会放大「只录到开头/1～2 个词」和「一大半没转出来」的体感。
- **网络上的共识**：流式 ASR 应先发送结束/定型信号并等待最终结果，再关连接或使用转录；豆包以 `is_last` 标识最终结果；VAD 静默建议 1.4～2 秒以减少句中截断。
- 优先做 **P0**：在 stop_audio 分支用 **`await asr.stop_stream()` 取转录**（替代先 `get_full_transcript()` 再后置 `stop_stream()`），与 openrouter、gpt4o 批量 ASR、测试用例及外部文档一致。再按需做 P1（redemptionMs 1500～2000）、P2（豆包超时/长句）。
