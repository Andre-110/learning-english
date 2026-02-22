#!/usr/bin/env python3
"""
测试FunASR本地部署
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from services.funasr_service import FunASRService
from services.speech import SpeechServiceFactory
import io

def test_funasr_service():
    """测试FunASR服务"""
    print("=" * 60)
    print("测试FunASR本地部署")
    print("=" * 60)
    
    # 方式1: 使用模型名称（自动下载）
    print("\n1. 使用模型名称（自动下载）...")
    try:
        service1 = FunASRService(
            model_name="iic/SenseVoiceSmall",
            language="auto"
        )
        print("✅ FunASR服务创建成功")
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        return False
    
    # 方式2: 使用本地模型目录（如果已下载）
    print("\n2. 使用本地模型目录...")
    model_dir = os.getenv("FUNASR_MODEL_DIR")
    if model_dir and os.path.exists(model_dir):
        try:
            service2 = FunASRService(
                model_dir=model_dir,
                language="auto"
            )
            print(f"✅ 使用本地模型: {model_dir}")
        except Exception as e:
            print(f"⚠️  本地模型加载失败: {e}")
    else:
        print(f"⚠️  未配置本地模型目录（FUNASR_MODEL_DIR）")
    
    # 测试转录（如果有测试音频文件）
    print("\n3. 测试音频转录...")
    test_audio_paths = [
        "test_audio/test_simple.mp3",
        "test_audio/test_medium.mp3",
        "test_audio/test_simple.wav",
    ]
    
    test_audio_found = False
    for audio_path in test_audio_paths:
        if os.path.exists(audio_path):
            test_audio_found = True
            print(f"\n测试文件: {audio_path}")
            try:
                with open(audio_path, 'rb') as f:
                    audio_io = io.BytesIO(f.read())
                    result = service1.transcribe_audio(audio_io)
                    print(f"✅ 转录成功: {result}")
                    break
            except Exception as e:
                print(f"❌ 转录失败: {e}")
                import traceback
                traceback.print_exc()
    
    if not test_audio_found:
        print("⚠️  未找到测试音频文件，跳过转录测试")
    
    # 测试工厂方法
    print("\n4. 测试工厂方法...")
    try:
        service3 = SpeechServiceFactory.create(
            provider="funasr",
            model_name="iic/SenseVoiceSmall"
        )
        print("✅ 工厂方法创建成功")
    except Exception as e:
        print(f"❌ 工厂方法失败: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_funasr_service()
    sys.exit(0 if success else 1)


