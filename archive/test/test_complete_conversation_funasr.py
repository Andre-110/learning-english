#!/usr/bin/env python3
"""
使用FunASR本地部署完成完整的英语学习对话测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import requests
import json
import time
from config.settings import Settings

BASE_URL = "http://localhost:8000"

def get_available_audio_files():
    """获取可用的测试音频文件"""
    audio_dir = "test_audio"
    if not os.path.exists(audio_dir):
        return []
    
    audio_files = []
    for f in os.listdir(audio_dir):
        if f.endswith(('.mp3', '.wav', '.m4a', '.webm')):
            audio_files.append(os.path.join(audio_dir, f))
    
    return sorted(audio_files)

def test_complete_conversation():
    """测试完整的对话流程"""
    print("=" * 70)
    print("FunASR本地部署 - 完整对话流程测试")
    print("=" * 70)
    
    # 检查配置
    settings = Settings()
    print(f"\n📋 当前配置:")
    print(f"   SPEECH_PROVIDER: {settings.speech_provider}")
    print(f"   FUNASR_MODEL_NAME: {settings.funasr_model_name}")
    
    if settings.speech_provider != "funasr":
        print(f"\n⚠️  警告: SPEECH_PROVIDER 不是 'funasr'")
        print("   将使用配置的服务提供商")
    
    # 获取可用音频文件
    audio_files = get_available_audio_files()
    if not audio_files:
        print("\n❌ 未找到测试音频文件")
        return False
    
    print(f"\n📁 找到 {len(audio_files)} 个测试音频文件:")
    for i, f in enumerate(audio_files, 1):
        size = os.path.getsize(f) / 1024  # KB
        print(f"   {i}. {f} ({size:.1f} KB)")
    
    # 步骤1: 开始对话
    print("\n" + "=" * 70)
    print("步骤1: 开始对话")
    print("=" * 70)
    
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "test_user_complete"},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ 开始对话失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return False
        
        data = response.json()
        conversation_id = data['conversation_id']
        initial_question = data['initial_question']
        
        print(f"✅ 对话已开始")
        print(f"   对话ID: {conversation_id}")
        print(f"   初始问题: {initial_question[:150]}...")
        
    except Exception as e:
        print(f"❌ 开始对话失败: {e}")
        return False
    
    # 步骤2: 使用音频文件进行多轮对话
    print("\n" + "=" * 70)
    print("步骤2: 使用音频文件进行多轮对话")
    print("=" * 70)
    
    conversation_results = []
    
    # 使用前几个音频文件（如果有多个）
    test_rounds = min(len(audio_files), 3)  # 最多3轮
    
    for round_num in range(1, test_rounds + 1):
        audio_file = audio_files[round_num - 1]
        print(f"\n--- 第 {round_num} 轮对话 ---")
        print(f"📤 上传音频: {audio_file}")
        
        try:
            # 上传音频文件
            with open(audio_file, 'rb') as f:
                files = {
                    'audio_file': (
                        os.path.basename(audio_file),
                        f,
                        'audio/mpeg' if audio_file.endswith('.mp3') else 'audio/wav'
                    )
                }
                
                print("   ⏳ 正在转录和评估（FunASR本地处理）...")
                start_time = time.time()
                
                response = requests.post(
                    f"{BASE_URL}/conversations/{conversation_id}/respond-audio",
                    files=files,
                    timeout=120  # FunASR可能需要较长时间
                )
                
                elapsed_time = time.time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    
                    transcribed = data.get('transcribed_text', 'N/A')
                    assessment = data.get('assessment', {})
                    ability_profile = assessment.get('ability_profile', {})
                    next_question = data.get('next_question', 'N/A')
                    round_number = data.get('round_number', round_num)
                    
                    print(f"   ✅ 处理成功 (耗时: {elapsed_time:.2f}秒)")
                    print(f"   📝 转录文本: {transcribed}")
                    print(f"   📊 评估分数: {ability_profile.get('overall_score', 'N/A')}")
                    print(f"   🎯 CEFR等级: {ability_profile.get('cefr_level', 'N/A')}")
                    print(f"   💪 强项: {', '.join(ability_profile.get('strengths', [])) or '无'}")
                    print(f"   ⚠️  弱项: {', '.join(ability_profile.get('weaknesses', [])) or '无'}")
                    print(f"   ❓ 下一题: {next_question[:100]}...")
                    
                    conversation_results.append({
                        'round': round_number,
                        'transcribed': transcribed,
                        'score': ability_profile.get('overall_score'),
                        'level': ability_profile.get('cefr_level'),
                        'time': elapsed_time
                    })
                    
                    # 短暂延迟
                    time.sleep(1)
                    
                else:
                    print(f"   ❌ 处理失败: {response.status_code}")
                    print(f"   错误: {response.text}")
                    break
                    
        except requests.exceptions.Timeout:
            print(f"   ⏱️  请求超时（FunASR首次加载模型可能需要更长时间）")
            print(f"   建议: 增加超时时间或等待模型加载完成")
            break
        except Exception as e:
            print(f"   ❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            break
    
    # 步骤3: 获取对话信息
    print("\n" + "=" * 70)
    print("步骤3: 获取对话信息")
    print("=" * 70)
    
    try:
        response = requests.get(
            f"{BASE_URL}/conversations/{conversation_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 对话信息获取成功")
            print(f"   对话ID: {data.get('conversation_id')}")
            print(f"   用户ID: {data.get('user_id')}")
            print(f"   状态: {data.get('state')}")
            print(f"   对话轮数: {data.get('round_count')}")
            print(f"   当前问题: {data.get('current_question', 'N/A')[:100]}...")
        else:
            print(f"⚠️  获取对话信息失败: {response.status_code}")
    except Exception as e:
        print(f"⚠️  获取对话信息失败: {e}")
    
    # 步骤4: 总结
    print("\n" + "=" * 70)
    print("步骤4: 测试总结")
    print("=" * 70)
    
    if conversation_results:
        print(f"\n✅ 成功完成 {len(conversation_results)} 轮对话")
        print(f"\n📊 对话统计:")
        
        total_time = sum(r['time'] for r in conversation_results)
        avg_time = total_time / len(conversation_results)
        scores = [r['score'] for r in conversation_results if r['score']]
        
        print(f"   总耗时: {total_time:.2f}秒")
        print(f"   平均耗时: {avg_time:.2f}秒/轮")
        
        if scores:
            print(f"   分数范围: {min(scores):.1f} - {max(scores):.1f}")
            print(f"   平均分数: {sum(scores)/len(scores):.1f}")
        
        print(f"\n📝 各轮详情:")
        for r in conversation_results:
            print(f"   第{r['round']}轮: {r['transcribed'][:50]}... | "
                  f"分数: {r['score']} | CEFR: {r['level']} | "
                  f"耗时: {r['time']:.2f}s")
    else:
        print("\n⚠️  未完成任何对话轮次")
    
    print("\n" + "=" * 70)
    print("✅ FunASR本地部署完整对话测试完成！")
    print("=" * 70)
    
    return len(conversation_results) > 0

def main():
    """主函数"""
    try:
        # 检查API是否可用
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code != 200:
            print("❌ API服务不可用")
            print("   请先启动服务: uvicorn api.main:app --reload")
            return False
    except:
        print("❌ 无法连接到API服务")
        print("   请先启动服务: uvicorn api.main:app --reload")
        return False
    
    success = test_complete_conversation()
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


