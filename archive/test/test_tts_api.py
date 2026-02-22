#!/usr/bin/env python3
"""
测试 TTS API 端点
"""
import sys
import os
import requests
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_BASE_URL = "http://localhost:8000"


def test_list_voices():
    """测试列出语音列表"""
    print("=" * 60)
    print("测试1: 列出可用语音")
    print("=" * 60)
    
    try:
        response = requests.get(f"{API_BASE_URL}/tts/voices?language=en", timeout=10)
        
        if response.status_code == 404:
            print("❌ API 端点未找到 (404)")
            print("   可能原因:")
            print("   1. 服务器需要重启以加载新的 TTS 路由")
            print("   2. TTS 模块导入失败")
            print("\n   请检查:")
            print("   - 服务器是否已重启")
            print("   - api/tts_endpoint.py 是否存在")
            print("   - 是否有导入错误")
            return None
        
        response.raise_for_status()
        
        data = response.json()
        print(f"\n✅ 成功获取 {data['total']} 个英语语音\n")
        
        print("前10个语音:")
        print("-" * 60)
        for i, voice in enumerate(data['voices'][:10], 1):
            print(f"{i:2d}. {voice['name']:30s} | {voice['locale']:10s} | {voice['gender']:6s}")
        
        return data['voices']
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到API服务器")
        print("   请确保服务器正在运行:")
        print("   cd /home/ubuntu/learning_english")
        print("   source venv/bin/activate")
        print("   uvicorn api.main:app --host 0.0.0.0 --port 8000")
        return None
    except Exception as e:
        print(f"❌ 错误: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   响应状态码: {e.response.status_code}")
            print(f"   响应内容: {e.response.text[:200]}")
        return None


def test_text_to_speech(text="Hello, this is a test.", voice="en-US-JennyNeural"):
    """测试文本转语音"""
    print("\n" + "=" * 60)
    print("测试2: 文本转语音")
    print("=" * 60)
    
    print(f"\n文本: {text}")
    print(f"语音: {voice}")
    print("-" * 60)
    
    try:
        params = {
            "text": text,
            "voice": voice
        }
        
        response = requests.post(
            f"{API_BASE_URL}/tts/text-to-speech",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        
        # 保存音频文件
        output_file = "test_tts_api_output.mp3"
        with open(output_file, "wb") as f:
            f.write(response.content)
        
        print(f"✅ 成功生成音频")
        print(f"   文件大小: {len(response.content)} 字节")
        print(f"   保存位置: {output_file}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到API服务器")
        print("   请确保服务器正在运行: uvicorn api.main:app --reload")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   响应内容: {e.response.text[:200]}")
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("TTS API 测试")
    print("=" * 60)
    
    # 测试1: 列出语音
    voices = test_list_voices()
    
    if voices:
        # 测试2: 文本转语音（使用第一个英语语音）
        test_voice = voices[0]['name'] if voices else "en-US-JennyNeural"
        test_text_to_speech(
            text="Hello! I'm testing the text-to-speech service.",
            voice=test_voice
        )
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()

