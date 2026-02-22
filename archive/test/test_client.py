#!/usr/bin/env python3
"""
简单的测试客户端 - 用于测试API功能
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def print_separator():
    print("=" * 60)

def test_health_check():
    """测试健康检查"""
    print("\n1. 健康检查...")
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print(f"✅ 服务运行正常: {response.json()}")
            return True
        else:
            print(f"❌ 服务异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到服务: {e}")
        print("   请确保服务已启动: uvicorn api.main:app --reload")
        return False

def test_start_conversation():
    """测试开始对话"""
    print("\n2. 开始对话...")
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "test_user_001"}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 对话已开始")
            print(f"   对话ID: {data['conversation_id']}")
            print(f"   初始问题: {data['initial_question']}")
            return data["conversation_id"]
        else:
            print(f"❌ 开始对话失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None

def test_respond(conversation_id, user_response):
    """测试回答问题"""
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/{conversation_id}/respond",
            json={"user_response": user_response}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ 回答已处理")
            print(f"   下一题: {data['next_question']}")
            print(f"   评估分数: {data['assessment']['ability_profile']['overall_score']:.1f}/100")
            print(f"   CEFR等级: {data['assessment']['ability_profile']['cefr_level']}")
            
            if data['assessment']['ability_profile']['strengths']:
                print(f"   强项: {', '.join(data['assessment']['ability_profile']['strengths'])}")
            if data['assessment']['ability_profile']['weaknesses']:
                print(f"   弱项: {', '.join(data['assessment']['ability_profile']['weaknesses'])}")
            
            print(f"   轮次: {data['round_number']}")
            return data
        else:
            print(f"❌ 回答处理失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None

def test_get_conversation(conversation_id):
    """测试获取对话信息"""
    print("\n3. 获取对话信息...")
    try:
        response = requests.get(f"{BASE_URL}/conversations/{conversation_id}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 对话信息获取成功")
            print(f"   对话ID: {data['conversation_id']}")
            print(f"   用户ID: {data['user_id']}")
            print(f"   状态: {data['state']}")
            print(f"   轮次: {data['round_count']}")
            if data.get('current_question'):
                print(f"   当前问题: {data['current_question']}")
            return True
        else:
            print(f"❌ 获取对话信息失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def interactive_test():
    """交互式测试"""
    print_separator()
    print("LinguaCoach API 测试客户端")
    print_separator()
    
    # 健康检查
    if not test_health_check():
        return
    
    # 开始对话
    conversation_id = test_start_conversation()
    if not conversation_id:
        return
    
    # 交互式问答
    print_separator()
    print("开始交互式对话（输入空行退出）")
    print_separator()
    
    round_num = 1
    while True:
        user_input = input(f"\n[第{round_num}轮] 你的回答: ").strip()
        if not user_input:
            print("\n对话结束")
            break
        
        result = test_respond(conversation_id, user_input)
        if not result:
            break
        
        round_num += 1
    
    # 获取最终对话信息
    test_get_conversation(conversation_id)
    
    print_separator()
    print("测试完成！")
    print_separator()

if __name__ == "__main__":
    try:
        interactive_test()
    except KeyboardInterrupt:
        print("\n\n测试中断")
        sys.exit(0)

