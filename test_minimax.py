#!/usr/bin/env python3
"""测试 MiniMax TTS API Key"""
import asyncio
import json
import os
import websockets
from dotenv import load_dotenv

load_dotenv()

async def test_minimax():
    api_key = os.getenv('MINIMAX_API_KEY')
    if not api_key:
        print("❌ MINIMAX_API_KEY 未设置")
        return
    
    print(f"API Key 前缀: {api_key[:30]}...")
    
    headers = {'Authorization': f'Bearer {api_key}'}
    endpoint = 'wss://api.minimaxi.com/ws/v1/t2a_v2'
    
    print(f"连接 {endpoint}...")
    try:
        async with websockets.connect(endpoint, extra_headers=headers, close_timeout=10) as ws:
            print("✅ WebSocket 连接成功!")
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(response)
            print(f"响应: {json.dumps(data, indent=2)}")
            
            if data.get("event") == "connected_success":
                print("✅ API Key 有效!")
            else:
                print(f"⚠️ 未知响应: {data}")
                
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ HTTP 错误: {e.status_code}")
    except websockets.exceptions.ConnectionClosedOK as e:
        print(f"❌ 连接被关闭 (OK): code={e.code}, reason={e.reason}")
        print("   可能原因: API Key 无效或已过期")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"❌ 连接错误: code={e.code}, reason={e.reason}")
    except asyncio.TimeoutError:
        print("❌ 连接超时")
    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_minimax())
