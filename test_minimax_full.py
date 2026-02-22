#!/usr/bin/env python3
"""完整测试 MiniMax TTS API 调用流程"""
import asyncio
import json
import os
import websockets
from dotenv import load_dotenv

load_dotenv()

async def test_minimax_full():
    api_key = os.getenv('MINIMAX_API_KEY')
    if not api_key:
        print("❌ MINIMAX_API_KEY 未设置")
        return
    
    print(f"API Key 前缀: {api_key[:30]}...")
    
    headers = {'Authorization': f'Bearer {api_key}'}
    endpoint = 'wss://api.minimaxi.com/ws/v1/t2a_v2'
    
    # 测试两种模型
    for model in ['speech-2.6', 'speech-2.6-hd']:
        print(f"\n{'='*50}")
        print(f"测试模型: {model}")
        print(f"{'='*50}")
        
        try:
            async with websockets.connect(endpoint, extra_headers=headers, close_timeout=10) as ws:
                # Step 1: 等待连接确认
                print("Step 1: 等待连接确认...")
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(response)
                print(f"  响应: {data}")
                
                if data.get("event") != "connected_success":
                    print(f"  ❌ 连接失败")
                    continue
                print("  ✅ 连接成功")
                
                # Step 2: 发送 task_start
                print("Step 2: 发送 task_start...")
                start_msg = {
                    "event": "task_start",
                    "model": model,
                    "voice_setting": {
                        "voice_id": "male-qn-jingying",
                        "speed": 1.0,
                        "vol": 1.0,
                        "pitch": 0,
                        "english_normalization": False
                    },
                    "audio_setting": {
                        "sample_rate": 32000,
                        "bitrate": 128000,
                        "format": "pcm",
                        "channel": 1
                    }
                }
                await ws.send(json.dumps(start_msg))
                print(f"  发送: {json.dumps(start_msg, indent=2)}")
                
                # Step 3: 等待 task_started
                print("Step 3: 等待 task_started...")
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(response)
                print(f"  响应: {data}")
                
                if data.get("event") != "task_started":
                    print(f"  ❌ 启动任务失败: {data}")
                    continue
                print("  ✅ 任务启动成功")
                
                # Step 4: 发送文本
                print("Step 4: 发送文本...")
                text_msg = {
                    "event": "task_continue",
                    "text": "Hello, this is a test."
                }
                await ws.send(json.dumps(text_msg))
                print("  ✅ 文本已发送")
                
                # Step 5: 接收音频
                print("Step 5: 接收音频...")
                audio_chunks = []
                while True:
                    response = await asyncio.wait_for(ws.recv(), timeout=10)
                    data = json.loads(response)
                    
                    if data.get("data") and data["data"].get("audio"):
                        audio_hex = data["data"]["audio"]
                        audio_bytes = bytes.fromhex(audio_hex)
                        audio_chunks.append(audio_bytes)
                        print(f"  收到音频块: {len(audio_bytes)} bytes")
                    
                    if data.get("is_final"):
                        print("  ✅ 接收完成")
                        break
                    
                    if data.get("event") == "error" or data.get("error"):
                        print(f"  ❌ 错误: {data}")
                        break
                
                total_bytes = sum(len(c) for c in audio_chunks)
                print(f"\n✅ 模型 {model} 测试成功！共 {len(audio_chunks)} 块，{total_bytes} bytes")
                
        except websockets.exceptions.ConnectionClosedOK as e:
            print(f"❌ 连接被关闭 (OK): code={e.code}, reason={e.reason}")
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"❌ 连接错误: code={e.code}, reason={e.reason}")
        except asyncio.TimeoutError:
            print("❌ 超时")
        except Exception as e:
            print(f"❌ 错误: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_minimax_full())
