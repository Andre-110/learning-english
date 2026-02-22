"""
测试 OpenAI Realtime API 连接

这个脚本直接测试与 OpenAI Realtime API 的连接，
不经过我们的服务层，用于验证 API 可用性。
"""
import asyncio
import json
import os
import sys
import base64
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# 尝试导入 websockets
try:
    import websockets
except ImportError:
    print("需要安装 websockets: pip install websockets")
    sys.exit(1)


async def test_realtime_connection():
    """测试 Realtime API 连接"""
    
    # 获取 API Key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ 错误: 未设置 OPENAI_API_KEY")
        return False
    
    print(f"📍 API Key: {api_key[:20]}...{api_key[-4:]}")
    
    # OpenAI Realtime WebSocket URL
    model = "gpt-4o-realtime-preview"
    url = f"wss://api.openai.com/v1/realtime?model={model}"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    print(f"\n🔗 连接到: {url}")
    print(f"📦 模型: {model}")
    
    try:
        start_time = time.time()
        
        async with websockets.connect(
            url,
            additional_headers=headers,
            ping_interval=30,
            ping_timeout=10
        ) as ws:
            connect_time = time.time() - start_time
            print(f"✅ WebSocket 连接成功! 耗时: {connect_time:.2f}秒")
            
            # 等待 session.created 事件
            print("\n⏳ 等待 session.created 事件...")
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            event = json.loads(response)
            
            if event.get("type") == "session.created":
                session = event.get("session", {})
                print(f"✅ 会话已创建!")
                print(f"   - Session ID: {session.get('id')}")
                print(f"   - Model: {session.get('model')}")
                print(f"   - Modalities: {session.get('modalities')}")
                print(f"   - Voice: {session.get('voice')}")
            else:
                print(f"⚠️ 收到意外事件: {event.get('type')}")
                print(f"   内容: {json.dumps(event, indent=2)[:500]}")
            
            # 更新会话配置
            print("\n📝 更新会话配置...")
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": "You are a helpful English tutor. Keep responses brief.",
                    "voice": "alloy",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    }
                }
            }
            await ws.send(json.dumps(session_update))
            
            # 等待 session.updated 确认
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            event = json.loads(response)
            
            if event.get("type") == "session.updated":
                print("✅ 会话配置更新成功!")
            else:
                print(f"⚠️ 收到: {event.get('type')}")
            
            # 发送一个文本消息测试
            print("\n💬 发送测试文本消息...")
            text_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Hello! Can you hear me?"
                        }
                    ]
                }
            }
            await ws.send(json.dumps(text_message))
            
            # 请求响应
            print("📤 请求 AI 响应...")
            response_request = {"type": "response.create"}
            await ws.send(json.dumps(response_request))
            
            # 收集响应
            response_text = ""
            audio_chunks = 0
            response_start = time.time()
            first_audio_time = None
            
            print("\n📥 接收响应事件:")
            while True:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=30)
                    event = json.loads(response)
                    event_type = event.get("type", "")
                    
                    if event_type == "response.audio.delta":
                        if first_audio_time is None:
                            first_audio_time = time.time()
                            latency = first_audio_time - response_start
                            print(f"   🔊 首个音频块! 延迟: {latency:.2f}秒")
                        audio_chunks += 1
                    
                    elif event_type == "response.audio_transcript.delta":
                        delta = event.get("delta", "")
                        response_text += delta
                        print(f"   📝 转录: {delta}", end="", flush=True)
                    
                    elif event_type == "response.text.delta":
                        delta = event.get("delta", "")
                        response_text += delta
                        print(f"   💬 文本: {delta}", end="", flush=True)
                    
                    elif event_type == "response.done":
                        total_time = time.time() - response_start
                        print(f"\n\n✅ 响应完成!")
                        print(f"   - 总耗时: {total_time:.2f}秒")
                        print(f"   - 音频块数: {audio_chunks}")
                        print(f"   - 响应文本: {response_text[:200]}...")
                        break
                    
                    elif event_type == "error":
                        error = event.get("error", {})
                        print(f"\n❌ 错误: {error.get('message')}")
                        print(f"   类型: {error.get('type')}")
                        print(f"   代码: {error.get('code')}")
                        break
                    
                    elif event_type in ["response.created", "response.output_item.added", 
                                       "response.content_part.added", "conversation.item.created",
                                       "response.output_item.done", "response.content_part.done",
                                       "response.audio.done", "response.audio_transcript.done"]:
                        # 正常流程事件，简单记录
                        pass
                    
                    elif event_type == "rate_limits.updated":
                        # 速率限制信息
                        pass
                    
                    else:
                        print(f"   📌 {event_type}")
                        
                except asyncio.TimeoutError:
                    print("\n⏰ 等待响应超时")
                    break
            
            print("\n" + "=" * 50)
            print("🎉 Realtime API 测试完成!")
            return True
            
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"\n❌ WebSocket 连接失败: HTTP {e.status_code}")
        if e.status_code == 401:
            print("   原因: API Key 无效或无权限")
        elif e.status_code == 403:
            print("   原因: 没有 Realtime API 访问权限")
        elif e.status_code == 429:
            print("   原因: 请求过多，请稍后重试")
        return False
    
    except Exception as e:
        print(f"\n❌ 连接错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_with_yunwu_proxy():
    """测试通过 yunwu.ai 代理连接"""
    
    print("\n" + "=" * 50)
    print("🔄 测试 yunwu.ai 代理...")
    print("=" * 50)
    
    # yunwu.ai 可能不支持 Realtime API 的 WebSocket 连接
    # 因为 Realtime API 需要直接的 WebSocket 连接到 OpenAI
    
    api_base = os.getenv("OPENAI_API_BASE", "")
    if "yunwu" in api_base.lower():
        print("⚠️ 检测到使用 yunwu.ai 代理")
        print("   Realtime API 需要直连 OpenAI，代理可能不支持 WebSocket")
        print("   建议: 使用原生 OpenAI API Key 进行 Realtime 连接")
    
    return False


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 OpenAI Realtime API 连接测试")
    print("=" * 50)
    
    # 检查环境变量
    api_base = os.getenv("OPENAI_API_BASE", "")
    print(f"\n📍 OPENAI_API_BASE: {api_base or '(未设置，使用默认)'}")
    
    if "yunwu" in api_base.lower():
        print("\n⚠️ 注意: 当前配置使用 yunwu.ai 代理")
        print("   Realtime API 是 WebSocket 协议，需要直连 OpenAI")
        print("   代理服务可能不支持 WebSocket 转发")
        print("\n   如果测试失败，请尝试:")
        print("   1. 使用原生 OpenAI API Key")
        print("   2. 或检查代理是否支持 WebSocket")
    
    # 运行测试
    success = asyncio.run(test_realtime_connection())
    
    if not success:
        print("\n💡 提示: 如果连接失败，可能的原因:")
        print("   1. API Key 没有 Realtime API 权限")
        print("   2. 使用的是代理服务，不支持 WebSocket")
        print("   3. 网络问题")
        print("\n   Realtime API 是 OpenAI 的新功能，需要:")
        print("   - 直连 OpenAI API (wss://api.openai.com)")
        print("   - 有效的 API Key 且有 Realtime 权限")
    
    sys.exit(0 if success else 1)

