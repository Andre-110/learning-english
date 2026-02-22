#!/usr/bin/env python3
"""
简单测试 edge-tts
"""
import asyncio
import edge_tts

async def test_simple():
    """简单测试"""
    print("测试 edge-tts...")
    
    # 直接使用已知的语音
    text = "Hello, this is a test."
    voice = "en-US-JennyNeural"
    
    print(f"文本: {text}")
    print(f"语音: {voice}")
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        print(f"✅ 成功生成音频，大小: {len(audio_data)} 字节")
        
        # 保存文件
        with open("test_tts_simple.mp3", "wb") as f:
            f.write(audio_data)
        print("✅ 音频已保存到 test_tts_simple.mp3")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_simple())

