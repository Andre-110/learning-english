#!/usr/bin/env python3
"""
听力测试 - 测试语音转文本功能（修复版）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
from pathlib import Path

BASE_URL = "http://localhost:8000"

def test_speech_transcription():
    """测试语音转文本功能"""
    print("=" * 70)
    print(" 听力测试 - 语音转文本功能")
    print("=" * 70)
    print()
    
    # 检查是否有测试音频文件（优先检查test_audio目录）
    audio_dir = Path("test_audio")
    if audio_dir.exists():
        audio_files = (
            list(audio_dir.glob("*.mp3")) + 
            list(audio_dir.glob("*.wav")) + 
            list(audio_dir.glob("*.m4a"))
        )
    else:
        audio_files = []
    
    # 如果test_audio目录没有文件，检查当前目录
    if not audio_files:
        audio_files = (
            list(Path(".").glob("*.mp3")) + 
            list(Path(".").glob("*.wav")) + 
            list(Path(".").glob("*.m4a"))
        )
    
    if not audio_files:
        print("⚠️  未找到测试音频文件")
        print("   请运行以下命令创建测试音频:")
        print("   python test/create_test_audio.py")
        return False
    
    print(f"   找到 {len(audio_files)} 个测试音频文件")
    
    # 开始对话
    print("\n1. 开始对话...")
    try:
        resp = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "listening_test"},
            timeout=30
        )
        if resp.status_code != 200:
            print(f"   ❌ 开始对话失败: {resp.status_code}")
            return False
        
        data = resp.json()
        conv_id = data["conversation_id"]
        print(f"   ✅ 对话已开始: {conv_id}")
    except Exception as e:
        print(f"   ❌ 开始对话失败: {e}")
        return False
    
    # 测试语音输入
    print()
    print("2. 测试语音转文本...")
    print("-" * 70)
    
    success_count = 0
    failed_count = 0
    
    for audio_file in audio_files[:3]:  # 最多测试3个文件
        file_path = str(audio_file)
        file_name = Path(file_path).name
        print(f"\n   测试文件: {file_name}")
        
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                print(f"   ❌ 文件不存在: {file_path}")
                failed_count += 1
                continue
            
            # 检查文件大小
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                print(f"   ❌ 文件为空")
                failed_count += 1
                continue
            
            print(f"   文件大小: {file_size/1024:.1f} KB")
            
            # 读取文件内容（在with语句外）
            with open(file_path, 'rb') as f:
                audio_data = f.read()
            
            # 确定Content-Type
            ext = Path(file_path).suffix.lower()
            content_type_map = {
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',
                '.m4a': 'audio/m4a',
                '.mp4': 'audio/mp4',
                '.webm': 'audio/webm'
            }
            content_type = content_type_map.get(ext, 'audio/mpeg')
            
            print(f"   发送请求到API...")
            
            # 准备文件上传（使用BytesIO）
            files = {
                'audio_file': (file_name, audio_data, content_type)
            }
            
            # 发送语音请求
            resp = requests.post(
                f"{BASE_URL}/conversations/{conv_id}/respond-audio",
                files=files,
                timeout=120
            )
            
            if resp.status_code != 200:
                print(f"   ❌ API调用失败: {resp.status_code}")
                try:
                    error_detail = resp.json()
                    print(f"   错误详情: {json.dumps(error_detail, ensure_ascii=False, indent=2)}")
                except:
                    print(f"   错误文本: {resp.text[:300]}")
                failed_count += 1
                continue
            
            data = resp.json()
            
            print(f"   ✅ 转录成功")
            print(f"      原始转录: {data.get('transcribed_text', 'N/A')}")
            print(f"      标准化文本: {data.get('normalized_text', 'N/A')}")
            
            if 'language_analysis' in data:
                lang_analysis = data['language_analysis']
                print(f"      语言分析:")
                print(f"        - 主要语言: {lang_analysis.get('primary_language', 'N/A')}")
                print(f"        - 是否混合: {lang_analysis.get('is_mixed', False)}")
            
            if 'assessment' in data:
                assessment = data['assessment']
                profile = assessment.get('ability_profile', {})
                print(f"      评估结果:")
                print(f"        - 分数: {profile.get('overall_score', 0):.1f}/100")
                print(f"        - CEFR等级: {profile.get('cefr_level', 'N/A')}")
            
            if 'next_question' in data:
                print(f"      下一题: {data['next_question'][:60]}...")
            
            success_count += 1
            
        except requests.exceptions.Timeout:
            print(f"   ❌ 请求超时")
            failed_count += 1
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            failed_count += 1
    
    # 测试总结
    print()
    print("=" * 70)
    print("测试总结")
    print("=" * 70)
    print(f"\n   成功: {success_count}个")
    print(f"   失败: {failed_count}个")
    print(f"   总计: {len(audio_files[:3])}个")
    
    if failed_count == 0 and success_count > 0:
        print("\n✅ 听力测试完成！所有测试通过！")
        return True
    elif success_count > 0:
        print(f"\n⚠️  听力测试部分成功：{success_count}个成功，{failed_count}个失败")
        return False
    else:
        print("\n❌ 听力测试失败！所有测试都失败了")
        print("\n可能的原因:")
        print("1. 音频文件格式问题")
        print("2. API端点处理multipart数据有问题")
        print("3. Whisper API调用失败")
        print("4. API配额或网络问题")
        return False

if __name__ == "__main__":
    try:
        success = test_speech_transcription()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试中断")
        exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)





