#!/usr/bin/env python3
"""
通过API端点测试FunASR完整对话流程
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import time
import json

BASE_URL = "http://localhost:8000"
TIMEOUT = 120  # 增加超时时间，因为FunASR首次加载模型需要时间

def test_complete_conversation_via_api():
    """通过API测试完整对话流程"""
    print("=" * 70)
    print("FunASR API端点 - 完整对话流程测试")
    print("=" * 70)
    
    # 获取音频文件
    audio_files = [
        "test_audio/test_simple.mp3",
        "test_audio/test_medium.mp3",
        "test_audio/test_mixed.mp3",
        "test_audio/test_advanced.mp3",
    ]
    
    available_files = [f for f in audio_files if os.path.exists(f)]
    
    if not available_files:
        print("❌ 未找到测试音频文件")
        return False
    
    print(f"\n📁 找到 {len(available_files)} 个测试音频文件:")
    for i, f in enumerate(available_files, 1):
        size = os.path.getsize(f) / 1024
        print(f"   {i}. {os.path.basename(f)} ({size:.1f} KB)")
    
    # 步骤1: 开始对话
    print("\n" + "=" * 70)
    print("步骤1: 开始对话")
    print("=" * 70)
    
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "test_user_funasr_api"},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        conversation_id = data["conversation_id"]
        initial_question = data.get("initial_question", "")
        
        print(f"✅ 对话已开始")
        print(f"   对话ID: {conversation_id}")
        print(f"   初始问题: {initial_question[:150]}...")
    except Exception as e:
        print(f"❌ 开始对话失败: {e}")
        if hasattr(e, 'response'):
            print(f"   响应: {e.response.text}")
        return False
    
    # 步骤2: 使用音频文件进行多轮对话
    print("\n" + "=" * 70)
    print("步骤2: 通过API上传音频并进行多轮对话")
    print("=" * 70)
    
    conversation_results = []
    test_rounds = min(len(available_files), 4)
    
    for round_num in range(1, test_rounds + 1):
        audio_file = available_files[round_num - 1]
        print(f"\n{'='*70}")
        print(f"第 {round_num} 轮对话")
        print(f"{'='*70}")
        print(f"📤 音频文件: {os.path.basename(audio_file)}")
        
        try:
            # 上传音频文件
            print("   ⏳ 上传音频并处理...")
            start_time = time.time()
            
            with open(audio_file, 'rb') as f:
                files = {'audio_file': (os.path.basename(audio_file), f, 'audio/mpeg')}
                response = requests.post(
                    f"{BASE_URL}/conversations/{conversation_id}/respond-audio",
                    files=files,
                    timeout=TIMEOUT
                )
            
            processing_time = time.time() - start_time
            
            if response.status_code != 200:
                print(f"   ❌ API调用失败: {response.status_code}")
                print(f"   错误: {response.text}")
                break
            
            data = response.json()
            
            # 显示结果
            assessment = data.get("assessment", {})
            ability_profile = assessment.get("ability_profile", {})
            transcribed_text = data.get("transcribed_text", "")
            next_question = data.get("next_question", "")
            
            print(f"   ✅ 处理完成 (耗时: {processing_time:.2f}秒)")
            print(f"   📝 转录文本: {transcribed_text[:100]}...")
            print(f"   📊 综合分数: {ability_profile.get('overall_score', 0):.1f}/100")
            print(f"   🎯 CEFR等级: {ability_profile.get('cefr_level', 'N/A')}")
            print(f"   💪 强项: {', '.join(ability_profile.get('strengths', [])) if ability_profile.get('strengths') else '无'}")
            print(f"   ⚠️  弱项: {', '.join(ability_profile.get('weaknesses', [])) if ability_profile.get('weaknesses') else '无'}")
            print(f"   ❓ 下一题: {next_question[:100]}...")
            
            conversation_results.append({
                'round': round_num,
                'file': os.path.basename(audio_file),
                'transcribed': transcribed_text,
                'score': ability_profile.get('overall_score', 0),
                'level': ability_profile.get('cefr_level', 'N/A'),
                'processing_time': processing_time
            })
            
            # 短暂延迟
            time.sleep(1)
            
        except requests.exceptions.Timeout:
            print(f"   ❌ 请求超时（>{TIMEOUT}秒）")
            print("   ⚠️  FunASR首次加载模型可能需要更长时间")
            break
        except Exception as e:
            print(f"   ❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            break
    
    # 步骤3: 获取最终用户画像
    print("\n" + "=" * 70)
    print("步骤3: 最终用户画像")
    print("=" * 70)
    
    try:
        response = requests.get(
            f"{BASE_URL}/users/test_user_funasr_api/profile",
            timeout=TIMEOUT
        )
        if response.status_code == 200:
            user_profile = response.json()
            print(f"✅ 用户画像:")
            print(f"   用户ID: {user_profile.get('user_id', 'N/A')}")
            print(f"   综合分数: {user_profile.get('overall_score', 0):.1f}/100")
            print(f"   CEFR等级: {user_profile.get('cefr_level', 'N/A')}")
            print(f"   对话轮数: {user_profile.get('conversation_count', 0)}")
            print(f"   强项: {', '.join(user_profile.get('strengths', [])) if user_profile.get('strengths') else '无'}")
            print(f"   弱项: {', '.join(user_profile.get('weaknesses', [])) if user_profile.get('weaknesses') else '无'}")
    except Exception as e:
        print(f"⚠️  获取用户画像失败: {e}")
    
    # 步骤4: 测试总结
    print("\n" + "=" * 70)
    print("步骤4: 测试总结")
    print("=" * 70)
    
    if conversation_results:
        print(f"\n✅ 成功完成 {len(conversation_results)} 轮对话")
        
        total_processing_time = sum(r['processing_time'] for r in conversation_results)
        scores = [r['score'] for r in conversation_results]
        
        print(f"\n📊 性能统计:")
        print(f"   总处理时间: {total_processing_time:.2f}秒")
        print(f"   平均处理时间: {total_processing_time/len(conversation_results):.2f}秒/轮")
        
        if scores:
            print(f"\n📈 分数统计:")
            print(f"   分数范围: {min(scores):.1f} - {max(scores):.1f}")
            print(f"   平均分数: {sum(scores)/len(scores):.1f}")
            print(f"   最新分数: {scores[-1]:.1f}")
        
        print(f"\n📝 各轮详情:")
        for r in conversation_results:
            print(f"\n   第{r['round']}轮: {os.path.basename(r['file'])}")
            print(f"     转录: {r['transcribed'][:60]}...")
            print(f"     分数: {r['score']:.1f} | CEFR: {r['level']}")
            print(f"     处理耗时: {r['processing_time']:.2f}s")
    else:
        print("\n⚠️  未完成任何对话轮次")
    
    print("\n" + "=" * 70)
    print("✅ FunASR API端点完整对话流程测试完成！")
    print("=" * 70)
    
    return len(conversation_results) > 0

def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("FunASR API端点 - 完整对话流程测试")
    print("=" * 70)
    
    # 检查API服务是否运行
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ API服务运行正常: {BASE_URL}")
        else:
            print(f"⚠️  API服务响应异常: {response.status_code}")
    except Exception as e:
        print(f"❌ 无法连接到API服务: {BASE_URL}")
        print(f"   错误: {e}")
        print("\n请确保API服务正在运行:")
        print("   uvicorn api.main:app --host 0.0.0.0 --port 8000")
        return False
    
    success = test_complete_conversation_via_api()
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


