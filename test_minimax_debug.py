#!/usr/bin/env python3
"""调试 MiniMax TTS - 检查发送文本后的响应"""
import asyncio
import json
import os
import websockets
from dotenv import load_dotenv

load_dotenv()

async def test():
    api_key = os.getenv('MINIMAX_API_KEY')
    headers = {'Authorization': f'Bearer {api_key}'}
    endpoint = 'wss://api.minimaxi.com/ws/v1/t2a_v2'
    
    try:
        async with websockets.connect(endpoint, extra_headers=headers, close_timeout=10) as ws:
            # 连接
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"1. 连接: {response}")
            
            # task_start
            start_msg = {
                "event": "task_start",
                "model": "speech-2.6-hd",
                "voice_setting": {
                    "voice_id": "male-qn-jingying",
                    "speed": 1.0,
                    "vol": 1.0,
                    "pitch": 0
                },
                "audio_setting": {
                    "sample_rate": 32000,
                    "bitrate": 128000,
                    "format": "pcm",
                    "channel": 1
                }
            }
            await ws.send(json.dumps(start_msg))
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"2. task_start: {response}")
            
            # task_continue
            text_msg = {
                "event": "task_continue",
                "text": "Hello"
            }
            await ws.send(json.dumps(text_msg))
            print(f"3. 已发送文本: {text_msg}")
            
            # 尝试接收多条消息
            print("4. 等待响应...")
            for i in range(10):
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=3)
                    data = json.loads(response)
                    
                    # 检查是否有错误
                    if data.get("base_resp", {}).get("status_code", 0) != 0:
                        print(f"   ❌ 错误响应: {data}")
                    elif data.get("data") and data["data"].get("audio"):
                        audio_len = len(bytes.fromhex(data["data"]["audio"]))
                        print(f"   ✅ 音频块 {i}: {audio_len} bytes, is_final={data.get('is_final')}")
                    else:
                        print(f"   其他: {data}")
                    
                    if data.get("is_final"):
                        print("   ✅ 完成！")
                        break
                except asyncio.TimeoutError:
                    print(f"   超时...")
                    break
                    
    except websockets.exceptions.ConnectionClosedOK as e:
        print(f"❌ 连接关闭: code={e.code}, reason={e.reason}")
        # 打印关闭前收到的数据
        if hasattr(e, 'rcvd') and e.rcvd:
            print(f"   关闭帧数据: {e.rcvd}")
    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test())
