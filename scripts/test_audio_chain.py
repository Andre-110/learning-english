import asyncio
import websockets
import json
import base64
import time
import struct
import math

# 配置
WS_URL = "ws://localhost:8000/ws/conversation?user_id=test_audio_bot"
SAMPLE_RATE = 16000
DURATION_SEC = 2.0

def generate_sine_wave(duration=2.0, freq=440.0, sample_rate=16000):
    """生成正弦波 PCM 数据 (模拟音频)"""
    num_samples = int(duration * sample_rate)
    audio_data = bytearray()
    for i in range(num_samples):
        # 生成 16-bit PCM
        sample = int(32767.0 * math.sin(2.0 * math.pi * freq * i / sample_rate))
        audio_data.extend(struct.pack('<h', sample))
    return audio_data

async def test_audio_chain():
    print(f"🔌 连接到: {WS_URL}")
    async with websockets.connect(WS_URL) as ws:
        print("✅ WebSocket 连接成功")
        
        # 1. 等待初始化消息
        try:
            init_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"📩 收到消息: {init_msg}")
        except asyncio.TimeoutError:
            print("⚠️ 等待初始化消息超时")

        # 2. 发送开始信号
        print("📤 发送 start 信号")
        await ws.send(json.dumps({"type": "start"}))
        
        # 3. 发送音频流
        print(f"🎤 发送音频流 ({DURATION_SEC}s)...")
        audio_data = generate_sine_wave(DURATION_SEC)
        chunk_size = 4096 # 每次发送字节数
        
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            # 发送二进制数据
            await ws.send(chunk)
            await asyncio.sleep(0.01) # 模拟实时发送
            
        # 4. 发送停止信号
        print("📤 发送 stop_audio 信号")
        await ws.send(json.dumps({"type": "stop_audio"}))
        
        # 5. 接收响应
        print("👂 等待响应...")
        start_time = time.time()
        
        while True:
            # 设置超时，避免无限等待
            if time.time() - start_time > 30:
                print("⏰ 超时退出")
                break
                
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                
                # 检查是文本还是二进制
                if isinstance(msg, str):
                    data = json.loads(msg)
                    mtype = data.get("type")
                    print(f"📩 [{mtype}] {str(data)[:100]}...")
                    
                    if mtype == "transcription":
                        print(f"   📝 转录结果: {data.get('text')}")
                    elif mtype == "text_chunk":
                        print(f"   🤖 AI 回复: {data.get('text')}")
                    elif mtype == "audio_end":
                        print("   🔊 TTS 音频结束")
                        # 收到音频结束，可以退出了
                        break
                    elif mtype == "error":
                        print(f"   ❌ 错误: {data.get('message')}")
                        break
                else:
                    print(f"📩 [Binary] 收到音频数据: {len(msg)} bytes")
                    
            except asyncio.TimeoutError:
                print("⚠️ 等待响应超时 (10s)")
                break
            except Exception as e:
                print(f"❌ 接收错误: {e}")
                break

if __name__ == "__main__":
    try:
        asyncio.run(test_audio_chain())
    except KeyboardInterrupt:
        print("\n用户中断")
