#!/usr/bin/env python3
"""
快速测试脚本
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health():
    """测试健康检查"""
    print("1. 测试健康检查...")
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ 服务运行正常: {response.json()}")
            return True
        else:
            print(f"   ❌ 服务异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ 无法连接到服务: {e}")
        print("   请确保服务已启动: uvicorn api.main:app --reload")
        return False

def test_start_conversation():
    """测试开始对话"""
    print("\n2. 测试开始对话...")
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "test_user_001"},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ 对话已开始")
            print(f"   对话ID: {data['conversation_id']}")
            print(f"   初始问题: {data['initial_question']}")
            return data["conversation_id"]
        else:
            print(f"   ❌ 开始对话失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return None
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        return None

def test_respond(conversation_id, user_response):
    """测试回答问题"""
    print(f"\n3. 测试回答问题...")
    print(f"   用户输入: {user_response}")
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/{conversation_id}/respond",
            json={"user_response": user_response},
            timeout=60
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ 回答处理成功")
            print(f"   下一题: {data['next_question']}")
            
            assessment = data['assessment']
            profile = assessment['ability_profile']
            print(f"   评估分数: {profile['overall_score']:.1f}/100")
            print(f"   CEFR等级: {profile['cefr_level']}")
            
            if profile['strengths']:
                print(f"   强项: {', '.join(profile['strengths'])}")
            if profile['weaknesses']:
                print(f"   弱项: {', '.join(profile['weaknesses'])}")
            
            return data
        else:
            print(f"   ❌ 回答处理失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return None
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("=" * 60)
    print(" LinguaCoach 快速测试")
    print("=" * 60)
    print()
    
    # 1. 健康检查
    if not test_health():
        return
    
    # 2. 开始对话
    conversation_id = test_start_conversation()
    if not conversation_id:
        return
    
    # 3. 测试回答（中英文混杂）
    test_responses = [
        "I am a student. 我喜欢读书。",
    ]
    
    for response in test_responses:
        result = test_respond(conversation_id, response)
        if not result:
            break
        time.sleep(1)
    
    print("\n" + "=" * 60)
    print(" 测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()

