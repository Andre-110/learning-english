#!/usr/bin/env python3
"""
直接测试 TTS 服务（不通过 API，用于调试）
"""
import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tts import EdgeTTSService


async def test_direct():
    """直接测试 TTS 服务"""
    print("=" * 60)
    print("直接测试 Edge-TTS 服务")
    print("=" * 60)
    
    # 创建服务实例
    tts_service = EdgeTTSService(default_voice="en-US-JennyNeural")
    
    # 测试1: 列出语音
    print("\n测试1: 列出英语语音...")
    try:
        voices = await tts_service._list_voices_async(language="en")
        print(f"✅ 找到 {len(voices)} 个英语语音\n")
        
        print("前10个语音:")
        print("-" * 60)
        for i, voice in enumerate(voices[:10], 1):
            print(f"{i:2d}. {voice.get('ShortName', 'N/A'):30s} | "
                  f"{voice.get('Locale', 'N/A'):10s} | "
                  f"{voice.get('Gender', 'N/A'):6s}")
        
    except Exception as e:
        print(f"❌ 列出语音失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 测试2: 生成语音
    print("\n" + "=" * 60)
    print("测试2: 生成语音...")
    print("=" * 60)
    
    test_text = "Hello! This is a test of the text-to-speech service."
    print(f"\n文本: {test_text}")
    print(f"语音: en-US-JennyNeural")
    print("-" * 60)
    
    try:
        audio_data = await tts_service._text_to_speech_async(
            text=test_text,
            voice="en-US-JennyNeural"
        )
        
        print(f"✅ 成功生成音频，大小: {len(audio_data)} 字节")
        
        # 保存文件
        output_file = "test_tts_direct_output.mp3"
        with open(output_file, "wb") as f:
            f.write(audio_data)
        
        print(f"✅ 音频已保存到: {output_file}")
        
    except Exception as e:
        print(f"❌ 生成语音失败: {e}")
        print("\n可能的原因:")
        print("1. 网络连接问题（无法访问 Microsoft Edge TTS 服务）")
        print("2. 防火墙阻止了连接")
        print("3. 服务暂时不可用")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_direct())

