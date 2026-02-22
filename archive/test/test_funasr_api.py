#!/usr/bin/env python3
"""
测试FunASR API端点
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8000"

def test_api_health():
    """测试API健康检查"""
    print("=" * 60)
    print("测试1: API健康检查")
    print("=" * 60)
    
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"✅ API响应: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ API健康检查失败: {e}")
        print("   请确保服务已启动: uvicorn api.main:app --reload")
        return False

def test_start_conversation():
    """测试开始对话"""
    print("\n" + "=" * 60)
    print("测试2: 开始对话")
    print("=" * 60)
    
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "test_user_funasr"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 对话已开始")
            print(f"   对话ID: {data['conversation_id']}")
            print(f"   初始问题: {data['initial_question'][:100]}...")
            return data['conversation_id']
        else:
            print(f"❌ 开始对话失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 开始对话失败: {e}")
        return None

def test_audio_upload(conversation_id):
    """测试音频文件上传"""
    print("\n" + "=" * 60)
    print("测试3: 音频文件上传（FunASR转录）")
    print("=" * 60)
    
    if not conversation_id:
        print("⚠️  跳过：没有有效的对话ID")
        return False
    
    # 查找测试音频文件
    test_files = [
        "test_audio/test_simple.mp3",
        "test_audio/test_medium.mp3",
    ]
    
    test_file = None
    for f in test_files:
        if os.path.exists(f):
            test_file = f
            break
    
    if not test_file:
        print("⚠️  未找到测试音频文件")
        return False
    
    print(f"使用测试文件: {test_file}")
    
    try:
        with open(test_file, 'rb') as f:
            files = {'audio_file': (os.path.basename(test_file), f, 'audio/mpeg')}
            response = requests.post(
                f"{BASE_URL}/conversations/{conversation_id}/respond-audio",
                files=files,
                timeout=60  # 增加超时时间，FunASR首次加载模型需要时间
            )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 音频上传和转录成功")
            print(f"   转录文本: {data.get('transcribed_text', 'N/A')}")
            print(f"   标准化文本: {data.get('normalized_text', 'N/A')}")
            print(f"   评估分数: {data.get('assessment', {}).get('ability_profile', {}).get('overall_score', 'N/A')}")
            print(f"   CEFR等级: {data.get('assessment', {}).get('ability_profile', {}).get('cefr_level', 'N/A')}")
            print(f"   下一题: {data.get('next_question', 'N/A')[:100]}...")
            return True
        else:
            print(f"❌ 音频上传失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 音频上传失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("FunASR API端点测试")
    print("=" * 60)
    
    # 检查配置
    from config.settings import Settings
    settings = Settings()
    print(f"\n当前配置:")
    print(f"  SPEECH_PROVIDER: {settings.speech_provider}")
    
    if settings.speech_provider != "funasr":
        print("\n⚠️  警告: SPEECH_PROVIDER 不是 'funasr'")
        print("   当前将使用配置的服务提供商")
    
    # 测试API健康
    if not test_api_health():
        print("\n❌ API服务未启动，请先启动服务:")
        print("   uvicorn api.main:app --reload")
        return False
    
    # 开始对话
    conversation_id = test_start_conversation()
    
    # 测试音频上传
    if conversation_id:
        test_audio_upload(conversation_id)
    
    print("\n" + "=" * 60)
    print("✅ API测试完成！")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

