"""
OpenRouter Audio 端到端延迟测试

测试完整流程：Audio → GPT-4o Audio → TTS
"""
import asyncio
import base64
import json
import os
import sys
import time
import struct
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import websockets


def generate_test_audio_wav(duration_seconds=2, sample_rate=16000):
    """生成测试用的 WAV 音频"""
    num_samples = int(sample_rate * duration_seconds)
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        # 生成简单的音调
        sample = int(32767 * 0.3 * math.sin(2 * math.pi * 440 * t))
        samples.append(sample)
    
    audio_data = struct.pack('<' + 'h' * len(samples), *samples)
    
    wav_header = struct.pack('<4sI4s', b'RIFF', 36 + len(audio_data), b'WAVE')
    fmt_chunk = struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    data_chunk = struct.pack('<4sI', b'data', len(audio_data))
    
    return wav_header + fmt_chunk + data_chunk + audio_data


async def test_openrouter_audio_endpoint():
    """测试 OpenRouter Audio WebSocket 端点"""
    print("=" * 60)
    print("🧪 OpenRouter Audio 端到端延迟测试")
    print("=" * 60)
    
    # 服务器地址
    ws_url = "ws://localhost:8000/ws/openrouter-audio?user_level=B1"
    
    print(f"\n[1] 连接到 WebSocket: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as ws:
            print("    ✅ 连接成功")
            
            # 等待 ready 消息
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            print(f"    状态: {data.get('status')} - {data.get('message')}")
            
            # 生成测试音频
            print("\n[2] 生成测试音频...")
            audio_data = generate_test_audio_wav(duration_seconds=2)
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            print(f"    音频大小: {len(audio_data)} bytes")
            
            # 发送音频
            print("\n[3] 发送音频...")
            send_start = time.time()
            await ws.send(json.dumps({
                "type": "audio",
                "data": audio_base64,
                "format": "wav"
            }))
            
            # 等待响应
            print("\n[4] 等待响应...")
            
            first_response_time = None
            transcription = None
            evaluation = None
            response_text = ""
            audio_received = False
            latency_info = None
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    data = json.loads(msg)
                    msg_type = data.get("type")
                    
                    current_time = time.time() - send_start
                    
                    if msg_type == "response":
                        if first_response_time is None:
                            first_response_time = current_time
                            print(f"    ⚡ 首个响应: {first_response_time:.2f}s")
                        
                        if data.get("is_delta"):
                            response_text += data.get("text", "")
                            print(f"    📝 ", end="", flush=True)
                        else:
                            response_text = data.get("text", "")
                            print(f"\n    📝 完整响应: {response_text[:100]}...")
                    
                    elif msg_type == "transcription":
                        transcription = data.get("text")
                        print(f"    🎤 转录: {transcription}")
                    
                    elif msg_type == "evaluation":
                        evaluation = data.get("data")
                        score = evaluation.get("overall_score", "N/A")
                        level = evaluation.get("cefr_level", "N/A")
                        print(f"    📊 评估: 分数={score}, 等级={level}")
                    
                    elif msg_type == "audio":
                        audio_received = True
                        audio_size = len(base64.b64decode(data.get("data", "")))
                        print(f"    🔊 收到音频: {audio_size} bytes, 耗时: {current_time:.2f}s")
                    
                    elif msg_type == "done":
                        latency_info = data.get("latency", {})
                        print(f"\n    ✅ 处理完成!")
                        break
                    
                    elif msg_type == "error":
                        print(f"\n    ❌ 错误: {data.get('message')}")
                        break
                    
                    elif msg_type == "status":
                        print(f"    📌 状态: {data.get('status')}")
                        
                except asyncio.TimeoutError:
                    print("\n    ⏰ 等待超时")
                    break
            
            # 打印延迟分析
            print("\n" + "=" * 60)
            print("📊 延迟分析")
            print("=" * 60)
            
            if latency_info:
                llm_time = latency_info.get("llm", "N/A")
                tts_time = latency_info.get("tts", "N/A")
                total_time = latency_info.get("total", "N/A")
                
                print(f"    LLM 处理:    {llm_time:.2f}s" if isinstance(llm_time, (int, float)) else f"    LLM 处理:    {llm_time}")
                print(f"    TTS 生成:    {tts_time:.2f}s" if isinstance(tts_time, (int, float)) else f"    TTS 生成:    {tts_time}")
                print(f"    总延迟:      {total_time:.2f}s" if isinstance(total_time, (int, float)) else f"    总延迟:      {total_time}")
            
            if first_response_time:
                print(f"    首响应延迟:  {first_response_time:.2f}s")
            
            print("\n" + "=" * 60)
            print("📋 结果汇总")
            print("=" * 60)
            print(f"    转录: {'✅' if transcription else '❌'}")
            print(f"    评估: {'✅' if evaluation else '❌'}")
            print(f"    响应: {'✅' if response_text else '❌'}")
            print(f"    音频: {'✅' if audio_received else '❌'}")
            
            return True
            
    except websockets.exceptions.ConnectionRefused:
        print("    ❌ 连接被拒绝 - 服务器可能未运行")
        print("\n    请先启动服务器:")
        print("    cd /home/ubuntu/learning_english && source venv/bin/activate")
        print("    uvicorn api.main:app --host 0.0.0.0 --port 8000")
        return False
    except Exception as e:
        print(f"    ❌ 错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_info_endpoint():
    """测试 info 端点"""
    import aiohttp
    
    print("\n" + "=" * 60)
    print("📋 测试 Info 端点")
    print("=" * 60)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/openrouter-audio/info") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"    状态: {data.get('status')}")
                    print(f"    描述: {data.get('description')}")
                    print(f"    预期延迟: {data.get('expected_latency')}")
                    return True
                else:
                    print(f"    ❌ HTTP {resp.status}")
                    return False
    except Exception as e:
        print(f"    ❌ {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 OpenRouter Audio 端到端测试")
    print("=" * 60)
    
    # 测试 info 端点
    try:
        import aiohttp
        asyncio.run(test_info_endpoint())
    except ImportError:
        print("⚠️ 需要 aiohttp 来测试 info 端点")
    
    # 测试 WebSocket 端点
    success = asyncio.run(test_openrouter_audio_endpoint())
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 测试完成!")
    else:
        print("❌ 测试失败")
    print("=" * 60)

