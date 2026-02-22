# 性能优化指南

## 当前状态

### FunASR本地模型性能
- **首次加载**：~7-17秒（已优化，之前是23秒）
- **后续转录**：0.6-0.8秒
- **平均时间**：3.87秒（排除首次加载）

### 优势
- ✅ 无需网络连接
- ✅ 数据隐私好（本地处理）
- ✅ 无API费用
- ✅ 模型加载后速度稳定

### 劣势
- ⚠️ 首次加载需要7-17秒
- ⚠️ 需要本地资源（CPU/内存）
- ⚠️ 模型文件较大

## 切换到Whisper API

### 性能预期

根据OpenAI官方文档和实际测试，Whisper API通常：
- **响应时间**：1-3秒（取决于音频长度）
- **无需模型加载**：API端已预热
- **网络延迟**：取决于网络质量（通常100-500ms）

### 预期性能对比

| 指标 | FunASR本地 | Whisper API | 说明 |
|------|------------|-------------|------|
| 首次请求 | 7-17秒 | 1-3秒 | API无需加载模型 |
| 后续请求 | 0.6-0.8秒 | 1-3秒 | API可能稍慢但稳定 |
| 网络要求 | 无 | 需要稳定网络 | API依赖网络 |
| 成本 | 免费 | 按使用量收费 | API有费用 |

### 如何切换到Whisper API

#### 方法1：使用官方OpenAI API（推荐）

1. **修改环境变量**：
   ```bash
   # 编辑 .env 文件
   SPEECH_PROVIDER=whisper
   OPENAI_API_KEY=your_openai_api_key
   # 删除或注释掉 OPENAI_BASE_URL（使用官方API）
   # OPENAI_BASE_URL=
   ```

2. **重启服务**：
   ```bash
   pkill -f "uvicorn api.main:app"
   python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```

#### 方法2：使用支持Whisper的代理

如果必须使用代理，需要找到支持Whisper API的代理服务。

### 性能测试

运行对比测试：
```bash
python3 test_api_vs_local.py
```

## 进一步优化建议

### 1. 实时转录优化（已实施）✅
- 使用更小的音频块（1-2秒）
- 异步处理，不阻塞主流程
- 前端实时显示转录结果

### 2. 音频格式优化
- 使用更高效的格式（opus/webm）
- 降低采样率（16kHz足够）
- 压缩音频大小

### 3. 缓存优化
- 缓存常用音频的转录结果
- 使用Redis缓存用户画像

### 4. 并行处理（已实施）✅
- 对话处理和TTS准备并行执行
- 使用asyncio优化异步流程

### 5. GPU加速（如果有GPU）
- FunASR支持GPU加速
- 可以显著提升速度（5-10倍）

## 性能对比总结

### FunASR本地模型
- **适合场景**：
  - 需要数据隐私
  - 无稳定网络连接
  - 高频率使用（避免API费用）
  - 有GPU资源

- **性能**：
  - 首次加载：7-17秒（可通过预热解决）
  - 后续：0.6-0.8秒（非常快）

### Whisper API
- **适合场景**：
  - 需要快速响应
  - 网络稳定
  - 可以接受API费用
  - 不想管理本地模型

- **性能**：
  - 首次请求：1-3秒（无需加载）
  - 后续：1-3秒（稳定）

## 推荐方案

### 方案1：保持FunASR + 预热（当前方案）
- ✅ 已实施模型预热
- ✅ 首次加载后速度很快（0.6-0.8秒）
- ✅ 无需API费用
- ✅ 数据隐私好

**适用**：生产环境，高频率使用

### 方案2：切换到Whisper API
- ✅ 无需模型加载
- ✅ 首次请求即可快速响应
- ⚠️ 需要网络连接
- ⚠️ 有API费用

**适用**：需要快速响应，网络稳定，可以接受费用

### 方案3：混合方案
- 使用Whisper API作为主要服务
- FunASR作为备用（网络故障时）

## 实施步骤

### 切换到Whisper API

1. **检查API Key**：
   ```bash
   # 确保 .env 中有有效的 OPENAI_API_KEY
   grep OPENAI_API_KEY .env
   ```

2. **修改配置**：
   ```bash
   # 编辑 .env
   SPEECH_PROVIDER=whisper
   # 删除 OPENAI_BASE_URL 或设置为官方API
   ```

3. **测试**：
   ```bash
   python3 test_stt_performance.py
   ```

4. **重启服务**：
   ```bash
   pkill -f "uvicorn api.main:app"
   python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```

## 性能监控

定期运行性能测试：
```bash
# 测试STT性能
python3 test_stt_performance.py

# 测试完整流程
python3 test_streaming_voice.py
```

## 结论

**当前FunASR方案已经很好**：
- 通过预热，首次请求延迟已解决
- 后续请求速度很快（0.6-0.8秒）
- 无需API费用
- 数据隐私好

**如果切换到Whisper API**：
- 首次请求会更快（1-3秒 vs 7-17秒）
- 但后续请求可能稍慢（1-3秒 vs 0.6-0.8秒）
- 需要网络和API费用

**建议**：如果当前性能已满足需求，保持FunASR方案。如果需要更快的首次响应且可以接受API费用，可以切换到Whisper API。



