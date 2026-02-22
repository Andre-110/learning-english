#!/usr/bin/env python3
"""
简单的FunASR测试 - 直接测试转录功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import io
from services.speech import SpeechServiceFactory
from config.settings import Settings

def main():
    print("=" * 60)
    print("FunASR本地部署简单测试")
    print("=" * 60)
    
    # 检查配置
    settings = Settings()
    print(f"\n配置检查:")
    print(f"  SPEECH_PROVIDER: {settings.speech_provider}")
    print(f"  FUNASR_MODEL_NAME: {settings.funasr_model_name}")
    
    if settings.speech_provider != "funasr":
        print(f"\n⚠️  当前配置不是funasr，但继续测试...")
    
    # 创建FunASR服务
    print(f"\n创建FunASR服务...")
    try:
        service = SpeechServiceFactory.create(
            provider="funasr",
            model_name=settings.funasr_model_name,
            language=settings.funasr_language
        )
        print("✅ FunASR服务创建成功")
    except Exception as e:
        print(f"❌ 创建服务失败: {e}")
        return False
    
    # 测试转录
    test_file = "test_audio/test_simple.mp3"
    if not os.path.exists(test_file):
        print(f"\n⚠️  测试文件不存在: {test_file}")
        return False
    
    print(f"\n测试转录: {test_file}")
    print("（首次加载模型可能需要几秒钟）...")
    
    try:
        with open(test_file, 'rb') as f:
            audio_io = io.BytesIO(f.read())
            result = service.transcribe_audio(audio_io)
            print(f"\n✅ 转录成功!")
            print(f"   结果: {result}")
            return True
    except Exception as e:
        print(f"\n❌ 转录失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    print("\n" + "=" * 60)
    if success:
        print("✅ FunASR本地部署测试通过！")
    else:
        print("❌ FunASR本地部署测试失败")
    print("=" * 60)
    sys.exit(0 if success else 1)


