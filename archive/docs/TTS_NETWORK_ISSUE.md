# TTS 网络问题说明

## 问题描述

测试时出现 `No audio was received` 错误，这通常表示服务器无法访问 Microsoft Edge TTS 服务。

## 可能原因

1. **网络连接问题**
   - 服务器无法访问互联网
   - 防火墙阻止了对 Microsoft Edge TTS 服务的访问

2. **代理设置**
   - 服务器需要通过代理访问外网，但未配置代理

3. **服务暂时不可用**
   - Microsoft Edge TTS 服务可能暂时不可用

## 解决方案

### 方案1：检查网络连接

```bash
# 测试网络连接
ping -c 3 8.8.8.8

# 测试 DNS 解析
nslookup speech.platform.bing.com
```

### 方案2：配置代理（如果需要）

如果服务器需要通过代理访问外网，可以在代码中配置代理：

```python
import os
os.environ['HTTP_PROXY'] = 'http://proxy.example.com:8080'
os.environ['HTTPS_PROXY'] = 'http://proxy.example.com:8080'
```

### 方案3：使用本地 TTS 替代方案

如果无法访问 Microsoft Edge TTS 服务，可以考虑：

1. **pyttsx3**（离线 TTS）
   ```bash
   pip install pyttsx3
   ```

2. **gTTS**（Google TTS，需要网络）
   ```bash
   pip install gtts
   ```

3. **本地 TTS 模型**（如 Coqui TTS）

## 验证 TTS 服务

### 方法1：直接测试 edge-tts

```bash
# 安装 edge-tts CLI
pip install edge-tts

# 测试命令行工具
edge-tts --text "Hello world" --write-media test.mp3
```

### 方法2：Python 测试

```python
import asyncio
import edge_tts

async def test():
    communicate = edge_tts.Communicate("Hello world", "en-US-JennyNeural")
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            print(f"收到音频块: {len(chunk['data'])} 字节")

asyncio.run(test())
```

## 当前状态

- ✅ TTS 服务代码已正确实现
- ✅ API 端点已正确配置
- ⚠️ 需要网络连接才能使用 Microsoft Edge TTS
- ⚠️ 如果无法访问，可以考虑使用替代方案

## 建议

1. **开发环境**：确保服务器可以访问互联网
2. **生产环境**：如果网络受限，考虑使用本地 TTS 方案
3. **测试**：在配置完成后，先测试网络连接，再测试 TTS 功能

