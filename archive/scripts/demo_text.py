#!/usr/bin/env python3
"""
基础文本对话Demo - 演示完整工作流程
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def print_section(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def demo_text_conversation():
    """演示文本对话流程"""
    
    print_section("Demo: 文本对话流程")
    
    # 1. 开始对话
    print("\n1️⃣ 开始对话...")
    response = requests.post(
        f"{BASE_URL}/conversations/start",
        json={"user_id": "demo_user_001"}
    )
    assert response.status_code == 200, f"开始对话失败: {response.status_code}"
    
    data = response.json()
    conversation_id = data["conversation_id"]
    print(f"✅ 对话已开始")
    print(f"   对话ID: {conversation_id}")
    print(f"   初始问题: {data['initial_question']}")
    
    # 2. 多轮对话
    test_responses = [
        "I am a student. 我喜欢读书。",  # 中英文混杂
        "I think reading can help us learn new things and improve our English.",
        "Yes, I read books every day. 我每天读30分钟。",
    ]
    
    for i, user_response in enumerate(test_responses, 1):
        print(f"\n{i+1}️⃣ 第{i}轮回答")
        print(f"   用户输入: {user_response}")
        
        # 发送回答
        response = requests.post(
            f"{BASE_URL}/conversations/{conversation_id}/respond",
            json={"user_response": user_response}
        )
        assert response.status_code == 200, f"回答失败: {response.status_code}"
        
        data = response.json()
        
        # 显示评估结果
        assessment = data["assessment"]
        profile = assessment["ability_profile"]
        
        print(f"   ✅ 评估结果:")
        print(f"      综合分数: {profile['overall_score']:.1f}/100")
        print(f"      CEFR等级: {profile['cefr_level']}")
        print(f"      强项: {', '.join(profile['strengths']) if profile['strengths'] else '无'}")
        print(f"      弱项: {', '.join(profile['weaknesses']) if profile['weaknesses'] else '无'}")
        
        # 显示维度评分
        print(f"   📊 维度评分:")
        for dim in assessment["dimension_scores"]:
            print(f"      {dim['dimension']}: {dim['score']:.1f}/5 - {dim['comment']}")
        
        # 显示下一题
        print(f"   ❓ 下一题: {data['next_question']}")
        
        # 显示用户画像更新
        user_profile = data["user_profile"]
        print(f"   👤 用户画像:")
        print(f"      综合分数: {user_profile['overall_score']:.1f}/100")
        print(f"      CEFR等级: {user_profile['cefr_level']}")
        print(f"      对话轮数: {user_profile['conversation_count']}")
        
        time.sleep(1)  # 避免请求过快
    
    # 3. 获取对话信息
    print(f"\n📋 获取对话信息...")
    response = requests.get(f"{BASE_URL}/conversations/{conversation_id}")
    assert response.status_code == 200
    
    data = response.json()
    print(f"   对话状态: {data['state']}")
    print(f"   总轮数: {data['round_count']}")
    
    print_section("Demo完成")
    return conversation_id

if __name__ == "__main__":
    try:
        demo_text_conversation()
    except Exception as e:
        print(f"\n❌ Demo失败: {e}")
        import traceback
        traceback.print_exc()





