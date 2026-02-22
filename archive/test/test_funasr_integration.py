#!/usr/bin/env python3
"""
测试FunASR本地部署集成到英语学习系统
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import io
from services.speech import SpeechServiceFactory
from services.realtime_speech import create_realtime_speech_service
from config.settings import Settings

def test_funasr_service():
    """测试FunASR服务"""
    print("=" * 60)
    print("测试1: FunASR服务直接调用")
    print("=" * 60)
    
    # 创建FunASR服务
    service = SpeechServiceFactory.create(provider="funasr")
    print("✅ FunASR服务创建成功")
    
    # 测试音频文件
    test_files = [
        "test_audio/test_simple.mp3",
        "test_audio/test_medium.mp3",
    ]
    
    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"\n测试文件: {test_file}")
            try:
                with open(test_file, 'rb') as f:
                    audio_io = io.BytesIO(f.read())
                    result = service.transcribe_audio(audio_io)
                    print(f"✅ 转录成功: {result}")
            except Exception as e:
                print(f"❌ 转录失败: {e}")
                import traceback
                traceback.print_exc()
            break
    else:
        print("⚠️  未找到测试音频文件")


def test_config_based_service():
    """测试基于配置的服务选择"""
    print("\n" + "=" * 60)
    print("测试2: 基于配置的服务选择")
    print("=" * 60)
    
    settings = Settings()
    print(f"当前配置: SPEECH_PROVIDER={settings.speech_provider}")
    
    if settings.speech_provider == "funasr":
        print("✅ 配置已切换到FunASR")
        
        # 使用配置创建服务
        service = SpeechServiceFactory.create(
            provider=settings.speech_provider,
            model_name=settings.funasr_model_name,
            language=settings.funasr_language
        )
        print(f"✅ 使用配置创建服务成功: model={settings.funasr_model_name}")
    else:
        print(f"⚠️  当前配置为: {settings.speech_provider}，不是funasr")


def test_realtime_speech_service():
    """测试实时语音服务集成FunASR"""
    print("\n" + "=" * 60)
    print("测试3: 实时语音服务集成FunASR")
    print("=" * 60)
    
    settings = Settings()
    
    # 根据配置创建语音服务
    if settings.speech_provider == "funasr":
        speech_service = SpeechServiceFactory.create(
            provider="funasr",
            model_name=settings.funasr_model_name,
            language=settings.funasr_language
        )
    else:
        speech_service = SpeechServiceFactory.create(provider="whisper")
    
    print(f"✅ 语音服务创建成功: provider={settings.speech_provider}")
    
    # 创建实时语音服务
    realtime_service = create_realtime_speech_service(speech_service=speech_service)
    print("✅ 实时语音服务创建成功")
    
    # 测试转录（模拟）
    test_file = "test_audio/test_simple.mp3"
    if os.path.exists(test_file):
        print(f"\n测试转录: {test_file}")
        try:
            with open(test_file, 'rb') as f:
                audio_io = io.BytesIO(f.read())
                result = speech_service.transcribe_audio(audio_io)
                print(f"✅ 转录成功: {result}")
        except Exception as e:
            print(f"❌ 转录失败: {e}")


def test_api_endpoint_simulation():
    """模拟API端点测试"""
    print("\n" + "=" * 60)
    print("测试4: 模拟API端点（语音文件上传）")
    print("=" * 60)
    
    from api.speech_endpoint import get_speech_service
    
    try:
        service = get_speech_service()
        print(f"✅ API端点获取服务成功: {type(service).__name__}")
        
        # 测试转录
        test_file = "test_audio/test_simple.mp3"
        if os.path.exists(test_file):
            print(f"\n测试转录: {test_file}")
            with open(test_file, 'rb') as f:
                audio_io = io.BytesIO(f.read())
                result = service.transcribe_audio(audio_io)
                print(f"✅ API端点转录成功: {result}")
    except Exception as e:
        print(f"❌ API端点测试失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("FunASR本地部署集成测试")
    print("=" * 60)
    
    # 检查配置
    settings = Settings()
    print(f"\n当前配置:")
    print(f"  SPEECH_PROVIDER: {settings.speech_provider}")
    print(f"  FUNASR_MODEL_NAME: {settings.funasr_model_name}")
    print(f"  FUNASR_LANGUAGE: {settings.funasr_language}")
    
    if settings.speech_provider != "funasr":
        print("\n⚠️  警告: SPEECH_PROVIDER 不是 'funasr'")
        print("   请在 .env 文件中设置: SPEECH_PROVIDER=funasr")
        print("   继续测试...")
    
    # 运行测试
    try:
        test_funasr_service()
        test_config_based_service()
        test_realtime_speech_service()
        test_api_endpoint_simulation()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


