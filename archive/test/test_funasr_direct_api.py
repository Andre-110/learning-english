#!/usr/bin/env python3
"""
直接测试FunASR API端点 - 绕过服务重启问题
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_direct_funasr():
    """直接测试FunASR功能"""
    print("=" * 70)
    print("FunASR本地部署 - 直接API测试")
    print("=" * 70)
    
    # 获取音频文件
    audio_files = [
        "test_audio/test_simple.mp3",
        "test_audio/test_medium.mp3",
        "test_audio/test_mixed.mp3",
    ]
    
    available_files = [f for f in audio_files if os.path.exists(f)]
    
    if not available_files:
        print("❌ 未找到测试音频文件")
        return False
    
    print(f"\n📁 找到 {len(available_files)} 个测试音频文件")
    
    # 开始对话
    print("\n" + "=" * 70)
    print("步骤1: 开始对话")
    print("=" * 70)
    
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "test_funasr_direct"},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ 失败: {response.status_code}")
            return False
        
        data = response.json()
        conversation_id = data['conversation_id']
        print(f"✅ 对话ID: {conversation_id}")
        print(f"   初始问题: {data['initial_question'][:100]}...")
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False
    
    # 测试每个音频文件
    print("\n" + "=" * 70)
    print("步骤2: 使用FunASR转录音频文件")
    print("=" * 70)
    
    results = []
    
    for i, audio_file in enumerate(available_files[:3], 1):  # 最多测试3个
        print(f"\n--- 测试 {i}/{min(len(available_files), 3)}: {os.path.basename(audio_file)} ---")
        
        try:
            with open(audio_file, 'rb') as f:
                files = {
                    'audio_file': (
                        os.path.basename(audio_file),
                        f,
                        'audio/mpeg'
                    )
                }
                
                print("   ⏳ 上传并处理中...")
                start_time = time.time()
                
                response = requests.post(
                    f"{BASE_URL}/conversations/{conversation_id}/respond-audio",
                    files=files,
                    timeout=120  # FunASR需要更长时间
                )
                
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    transcribed = data.get('transcribed_text', '')
                    assessment = data.get('assessment', {})
                    profile = assessment.get('ability_profile', {})
                    
                    print(f"   ✅ 成功 (耗时: {elapsed:.2f}秒)")
                    print(f"   📝 转录: {transcribed}")
                    print(f"   📊 分数: {profile.get('overall_score', 'N/A')}")
                    print(f"   🎯 等级: {profile.get('cefr_level', 'N/A')}")
                    print(f"   ❓ 下一题: {data.get('next_question', '')[:80]}...")
                    
                    results.append({
                        'file': os.path.basename(audio_file),
                        'transcribed': transcribed,
                        'score': profile.get('overall_score'),
                        'level': profile.get('cefr_level'),
                        'time': elapsed
                    })
                else:
                    error_detail = response.text
                    print(f"   ❌ 失败 ({response.status_code})")
                    print(f"   错误: {error_detail[:200]}")
                    
                    # 检查是否是FunASR相关错误
                    if "multipart" in error_detail or "EOF" in error_detail:
                        print(f"   ⚠️  这看起来像是Whisper API的错误")
                        print(f"   可能原因: 服务未重启，仍在使用旧配置")
                    
        except requests.exceptions.Timeout:
            print(f"   ⏱️  超时（FunASR首次加载可能需要更长时间）")
        except Exception as e:
            print(f"   ❌ 异常: {e}")
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    if results:
        print(f"\n✅ 成功处理 {len(results)} 个音频文件")
        for r in results:
            print(f"   {r['file']}: {r['transcribed'][:50]}... | "
                  f"分数: {r['score']} | 耗时: {r['time']:.2f}s")
    else:
        print("\n⚠️  未成功处理任何音频文件")
        print("   可能原因:")
        print("   1. 服务需要重启以加载新配置")
        print("   2. FunASR模型加载时间较长")
        print("   3. 音频文件格式问题")
    
    return len(results) > 0

if __name__ == "__main__":
    # 检查服务
    try:
        resp = requests.get(f"{BASE_URL}/", timeout=5)
        if resp.status_code != 200:
            print("❌ API服务不可用")
            sys.exit(1)
    except:
        print("❌ 无法连接到API服务")
        print("   请启动: uvicorn api.main:app --reload")
        sys.exit(1)
    
    success = test_direct_funasr()
    sys.exit(0 if success else 1)


