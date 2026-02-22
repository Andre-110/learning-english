#!/usr/bin/env python3
"""
测试 OpenAI TTS API（通过 yunwu.ai）
"""
import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tts import TTSServiceFactory
from config.llm_config import llm_config


async def test_openai_tts():
    """测试 OpenAI TTS"""
    print("=" * 60)
    print("测试 OpenAI TTS API（通过 yunwu.ai）")
    print("=" * 60)
    
    # 检查配置
    api_key = llm_config.get_openai_api_key()
    base_url = llm_config.get_openai_base_url()
    
    print(f"\n配置信息:")
    print(f"  API Key: {api_key[:10]}..." if api_key else "  API Key: 未设置")
    print(f"  Base URL: {base_url}")
    
    if not api_key:
        print("\n❌ 错误: 未设置 OPENAI_API_KEY")
        return False
    
    # 创建 TTS 服务
    print("\n创建 OpenAI TTS 服务...")
    try:
        tts_service = TTSServiceFactory.create(
            provider="openai",
            model="gpt-4o-mini-tts",  # yunwu.ai 使用的模型名
            default_voice="alloy"
        )
        print("✅ TTS 服务创建成功")
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        return False
    
    # 测试1: 列出语音
    print("\n" + "=" * 60)
    print("测试1: 列出可用语音")
    print("=" * 60)
    
    try:
        voices = tts_service.list_voices()
        print(f"\n✅ 找到 {len(voices)} 个语音\n")
        
        print("可用语音:")
        print("-" * 60)
        for voice in voices:
            print(f"  {voice['ShortName']:15s} | {voice['Gender']:10s} | {voice['FriendlyName']}")
        
    except Exception as e:
        print(f"❌ 列出语音失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试2: 生成语音
    print("\n" + "=" * 60)
    print("测试2: 生成语音")
    print("=" * 60)
    
    test_text = "Hello! This is a test of OpenAI text-to-speech service."
    test_voice = "alloy"
    
    print(f"\n文本: {test_text}")
    print(f"语音: {test_voice}")
    print("-" * 60)
    
    try:
        audio_data = await tts_service._text_to_speech_async(
            text=test_text,
            voice=test_voice
        )
        
        print(f"✅ 成功生成音频，大小: {len(audio_data)} 字节")
        
        # 保存文件
        output_file = "test_openai_tts_output.mp3"
        with open(output_file, "wb") as f:
            f.write(audio_data)
        
        print(f"✅ 音频已保存到: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ 生成语音失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_openai_tts())
    print("\n" + "=" * 60)
    print(f"测试结果: {'✅ 成功' if result else '❌ 失败'}")
    print("=" * 60)
    sys.exit(0 if result else 1)

