"""
测试 yunwu.ai 是否支持 Realtime API

yunwu.ai 是一个 OpenAI API 代理服务。
我们需要检查它是否支持 WebSocket 协议的 Realtime API。
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

try:
    import websockets
except ImportError:
    print("需要安装 websockets: pip install websockets")
    sys.exit(1)


async def test_yunwu_realtime():
    """测试 yunwu.ai 的 Realtime API 支持"""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ 错误: 未设置 OPENAI_API_KEY")
        return False
    
    print(f"📍 API Key: {api_key[:20]}...{api_key[-4:]}")
    
    # yunwu.ai 的可能 WebSocket 地址
    # 注意: 大多数代理服务不支持 WebSocket
    possible_urls = [
        "wss://yunwu.ai/v1/realtime?model=gpt-4o-realtime-preview",
        "wss://api.yunwu.ai/v1/realtime?model=gpt-4o-realtime-preview",
        "wss://yunwu.ai/realtime?model=gpt-4o-realtime-preview",
    ]
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    for url in possible_urls:
        print(f"\n🔗 尝试连接: {url}")
        
        try:
            async with websockets.connect(
                url,
                additional_headers=headers,
                ping_interval=30,
                ping_timeout=10
            ) as ws:
                print(f"✅ 连接成功!")
                
                # 等待初始事件
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                event = json.loads(response)
                print(f"   收到事件: {event.get('type')}")
                
                return True
                
        except websockets.exceptions.InvalidStatus as e:
            print(f"   ❌ HTTP {e.response.status_code}")
        except Exception as e:
            print(f"   ❌ {type(e).__name__}: {e}")
    
    return False


async def check_yunwu_api_info():
    """检查 yunwu.ai API 信息"""
    import aiohttp
    
    print("\n" + "=" * 50)
    print("📋 检查 yunwu.ai API 信息")
    print("=" * 50)
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = "https://yunwu.ai"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 检查可用模型
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/v1/models", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = data.get("data", [])
                    
                    print(f"\n📦 可用模型 ({len(models)} 个):")
                    
                    # 查找 realtime 相关模型
                    realtime_models = [m for m in models if "realtime" in m.get("id", "").lower()]
                    audio_models = [m for m in models if "audio" in m.get("id", "").lower()]
                    
                    if realtime_models:
                        print("\n🎯 Realtime 相关模型:")
                        for m in realtime_models:
                            print(f"   - {m.get('id')}")
                    else:
                        print("\n⚠️ 未找到 Realtime 相关模型")
                    
                    if audio_models:
                        print("\n🔊 Audio 相关模型:")
                        for m in audio_models:
                            print(f"   - {m.get('id')}")
                    
                    # 显示部分其他模型
                    print("\n📋 其他模型 (前10个):")
                    for m in models[:10]:
                        print(f"   - {m.get('id')}")
                    if len(models) > 10:
                        print(f"   ... 还有 {len(models) - 10} 个模型")
                        
                else:
                    print(f"❌ 获取模型列表失败: HTTP {resp.status}")
                    
    except Exception as e:
        print(f"❌ 请求失败: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 yunwu.ai Realtime API 支持测试")
    print("=" * 50)
    
    # 先检查 API 信息
    try:
        import aiohttp
        asyncio.run(check_yunwu_api_info())
    except ImportError:
        print("⚠️ 需要 aiohttp 来检查 API 信息")
    
    # 测试 Realtime 连接
    print("\n" + "=" * 50)
    print("🔌 测试 Realtime WebSocket 连接")
    print("=" * 50)
    
    success = asyncio.run(test_yunwu_realtime())
    
    if not success:
        print("\n" + "=" * 50)
        print("📌 结论")
        print("=" * 50)
        print("\n❌ yunwu.ai 可能不支持 Realtime API (WebSocket)")
        print("\n💡 解决方案:")
        print("   1. 使用原生 OpenAI API Key 直连 OpenAI")
        print("   2. 或者继续使用现有的 GPT-4o Audio 模式")
        print("      (STT → GPT-4o → TTS 三步流程)")
        print("\n📊 延迟对比:")
        print("   - Realtime API: ~500ms 首音频延迟")
        print("   - GPT-4o Audio: ~3-5s 总延迟")
        print("   - 标准流程:     ~8-11s 总延迟")

