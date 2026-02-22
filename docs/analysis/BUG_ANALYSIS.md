# 🐛 问题分析报告

## 📊 监控数据摘要

- **ASR 延迟**：平均 15.57s，最大 160.06s，P95 25.73s ⚠️
- **CPU 使用率**：100% ⚠️
- **WebSocket 连接**：121 个（但活跃对话为 0）⚠️
- **时间轴完整性**：部分对话缺失关键事件 ⚠️

---

## 🔍 问题 1：ASR 延迟计算错误

### 现象
- Round 5 显示 ASR 延迟 160.06s，但实际 ASR 处理只用了 4.07s

### 根本原因
**时间轴事件记录顺序错误**：

```
Round 5 时间轴：
  0.00s  client_speech_start
  0.08s  asr_start          ← ❌ 错误：在用户开始说话时记录
  ...
156.07s  server_audio_first ← ✅ 正确：服务器收到第一帧音频
160.14s  asr_end

计算：160.14 - 0.08 = 160.06s ❌
实际：160.14 - 156.07 = 4.07s ✅
```

**问题代码位置**：
- `api/gpt4o_pipeline_endpoint.py:1421-1430`：在收到 `server_audio_first` 时记录 `asr_start`
- 但某些情况下，`asr_start` 可能在 `server_audio_first` 之前就被记录了

### 影响
- 监控数据严重失真
- 无法准确评估 ASR 性能
- 告警误报（P99 延迟 34108ms）

---

## 🔍 问题 2：时间轴事件缺失

### 现象
- Round 6, 15, 21：缺失 `asr_end`, `llm_start`, `llm_first_token`, `tts_start`, `tts_first_chunk`
- Round 5：缺失 `client_audio_first`

### 根本原因

#### 2.1 对话被提前中断
- 用户关闭页面或网络断开
- WebSocket 异常断开，但 `finally` 块没有正确记录时间轴
- 某些异常导致处理流程提前退出

#### 2.2 `client_audio_first` 缺失
- 前端发送了 `timeline_event`，但后端可能没有正确处理
- 或者前端在音频播放前就断开了连接

### 影响
- 无法计算用户感知延迟（显示为 "-"）
- 统计指标不准确（P50/P95 计算基于不完整数据）

---

## 🔍 问题 3：WebSocket 连接泄漏

### 现象
- 监控显示 121 个 WebSocket 连接
- 但实际只有 3 个 ESTABLISHED 连接（`netstat`）
- 活跃对话为 0

### 根本原因

#### 3.1 `connection_closed()` 未被调用
- 异常退出时，`finally` 块可能没有执行到 `connection_closed()`
- 或者 `WebSocketDisconnect` 异常被捕获后没有调用 `connection_closed()`

#### 3.2 异常处理不完整
```python
# 当前代码 (api/gpt4o_pipeline_endpoint.py:2343-2351)
except Exception as e:
    logger.error(f"WebSocket 错误: {e}", exc_info=True)
    # ❌ 没有调用 connection_closed(user_id)
    # ❌ 没有 break，可能继续循环
```

### 影响
- 内存泄漏（每个连接占用资源）
- 监控数据不准确
- 可能导致服务性能下降

---

## 🔍 问题 4：WebSocket 断开后仍尝试接收

### 现象
```
ERROR: Cannot call "receive" once a disconnect message has been received.
```

### 根本原因
```python
# 当前代码 (api/gpt4o_pipeline_endpoint.py:877-879)
while True:
    try:
        message = await websocket.receive()  # ❌ 断开后仍可能执行
```

**问题场景**：
1. `WebSocketDisconnect` 异常被捕获
2. `break` 跳出循环
3. 但 `finally` 块或其他异步任务可能仍在运行
4. 或者异常处理逻辑有漏洞，导致继续循环

### 影响
- 日志中大量错误信息
- 可能影响服务稳定性

---

## 🔍 问题 5：CPU 使用率 100%

### 现象
- 监控显示 CPU 100%
- 但 `ps aux` 显示 uvicorn 进程 CPU 只有 0.4%

### 可能原因

#### 5.1 系统负载高
- 其他进程占用 CPU
- 系统监控工具本身消耗资源

#### 5.2 阻塞操作
- ASR 连接池的 keepalive 任务可能阻塞
- 大量并发 WebSocket 连接处理
- 日志写入频繁

#### 5.3 死循环或忙等待
- 某个异步任务陷入死循环
- 连接监控任务可能有问题

### 需要进一步调查
- 使用 `top` 或 `htop` 查看具体进程
- 检查是否有其他 Python 进程
- 分析系统负载平均值

---

## 📋 修复优先级

### 🔴 高优先级（立即修复）

1. **修复 ASR 延迟计算**
   - 确保 `asr_start` 只在 `server_audio_first` 之后记录
   - 修复时间轴事件记录顺序

2. **修复 WebSocket 连接泄漏**
   - 在 `except Exception` 块中调用 `connection_closed()`
   - 确保所有退出路径都清理连接计数

3. **修复 WebSocket 断开错误**
   - 在 `websocket.receive()` 前检查连接状态
   - 改进异常处理逻辑

### 🟡 中优先级（尽快修复）

4. **修复时间轴事件缺失**
   - 在 `finally` 块中确保记录所有已发生的事件
   - 改进异常处理，确保关键事件不丢失

5. **调查 CPU 使用率**
   - 确认是系统负载还是代码问题
   - 优化阻塞操作

---

## 🔧 建议的修复方案

### 1. ASR 延迟计算修复
```python
# 确保 asr_start 在 server_audio_first 之后记录
if frame_count == 1:
    first_frame_time = int(time.time() * 1000)
    pipeline_context["audio_first_frame_time"] = first_frame_time
    record_timeline_event(..., event_type="server_audio_first", ...)
    # ✅ 在 server_audio_first 之后记录 asr_start
    record_timeline_event(..., event_type="asr_start", timestamp_ms=first_frame_time, ...)
```

### 2. WebSocket 连接泄漏修复
```python
except WebSocketDisconnect:
    logger.info("WebSocket 断开")
    connection_closed(user_id)  # ✅ 确保调用
    break
except Exception as e:
    logger.error(f"WebSocket 错误: {e}", exc_info=True)
    connection_closed(user_id)  # ✅ 异常时也调用
    break  # ✅ 确保退出循环
finally:
    # ✅ 双重保险：确保连接计数正确
    try:
        connection_closed(user_id)
    except:
        pass
```

### 3. WebSocket 接收修复
```python
while True:
    try:
        # ✅ 检查连接状态
        if websocket.client_state.name != "CONNECTED":
            break
        message = await websocket.receive()
    except WebSocketDisconnect:
        break
    except Exception as e:
        logger.error(f"接收消息错误: {e}")
        break  # ✅ 异常时退出循环
```

---

## 📝 总结

主要问题：
1. **时间轴事件记录顺序错误** → ASR 延迟计算错误
2. **WebSocket 连接泄漏** → 资源浪费，监控不准确
3. **异常处理不完整** → 连接未清理，错误日志
4. **时间轴事件缺失** → 统计数据不完整

建议按优先级逐一修复，先解决连接泄漏和延迟计算问题。
