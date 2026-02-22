#!/usr/bin/env python3
"""
测试 edge-tts TTS 服务
"""
import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tts import TTSServiceFactory


async def test_list_voices():
    """测试列出语音列表"""
    print("=" * 60)
    print("测试1: 列出可用语音")
    print("=" * 60)
    
    tts_service = TTSServiceFactory.create(provider="edge-tts")
    
    # 列出所有英语语音
    voices = tts_service.list_voices(language="en")
    
    print(f"\n找到 {len(voices)} 个英语语音\n")
    print("前10个英语语音:")
    print("-" * 60)
    for i, voice in enumerate(voices[:10], 1):
        print(f"{i:2d}. {voice.get('ShortName', 'N/A'):30s} | "
              f"{voice.get('Locale', 'N/A'):10s} | "
              f"{voice.get('Gender', 'N/A'):6s}")
    
    return voices


async def test_text_to_speech():
    """测试文本转语音"""
    print("\n" + "=" * 60)
    print("测试2: 文本转语音")
    print("=" * 60)
    
    tts_service = TTSServiceFactory.create(provider="edge-tts")
    
    test_texts = [
        "Hello, this is a test of the text-to-speech service.",
        "I am a student. I like reading books.",
    ]
    
    for i, text in enumerate(test_texts, 1):
        print(f"\n测试文本 {i}: {text}")
        print("-" * 60)
        
        try:
            audio_data = tts_service.text_to_speech(text)
            print(f"✅ 成功生成音频，大小: {len(audio_data)} 字节")
            
            # 保存音频文件
            output_file = f"test_tts_output_{i}.mp3"
            with open(output_file, 'wb') as f:
                f.write(audio_data)
            print(f"✅ 音频已保存到: {output_file}")
            
        except Exception as e:
            print(f"❌ 生成音频失败: {e}")
            import traceback
            traceback.print_exc()


async def test_custom_voice():
    """测试自定义语音"""
    print("\n" + "=" * 60)
    print("测试3: 使用自定义语音")
    print("=" * 60)
    
    # 使用英语女性语音
    tts_service = TTSServiceFactory.create(
        provider="edge-tts",
        default_voice="en-US-JennyNeural"
    )
    
    text = "Hello! I'm Jenny, and I'm here to help you learn English."
    print(f"\n测试文本: {text}")
    print(f"使用语音: en-US-JennyNeural")
    print("-" * 60)
    
    try:
        audio_data = tts_service.text_to_speech(text)
        print(f"✅ 成功生成音频，大小: {len(audio_data)} 字节")
        
        output_file = "test_tts_custom_voice.mp3"
        with open(output_file, 'wb') as f:
            f.write(audio_data)
        print(f"✅ 音频已保存到: {output_file}")
        
    except Exception as e:
        print(f"❌ 生成音频失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Edge-TTS 服务测试")
    print("=" * 60)
    
    try:
        # 测试1: 列出语音
        voices = await test_list_voices()
        
        # 测试2: 文本转语音
        await test_text_to_speech()
        
        # 测试3: 自定义语音
        await test_custom_voice()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

