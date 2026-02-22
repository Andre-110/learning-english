#!/usr/bin/env python3
"""
快速评估功能测试 - 验证评估功能是否正常
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_assessment():
    """测试评估功能"""
    print("=" * 70)
    print(" 评估功能测试")
    print("=" * 70)
    print()
    
    # 1. 开始对话
    print("1. 开始对话...")
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "assessment_test"},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        conversation_id = data["conversation_id"]
        print(f"   ✅ 对话已开始: {conversation_id}")
        print(f"   初始问题: {data['initial_question'][:60]}...")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        return False
    
    # 2. 测试不同水平的回答
    test_cases = [
        {
            "name": "初级回答",
            "response": "I am student. I like book.",
            "expected_level": "A1-A2"
        },
        {
            "name": "中级回答",
            "response": "I am a student. I like reading books very much. Reading helps me learn new words and improve my English skills.",
            "expected_level": "B1-B2"
        },
        {
            "name": "高级回答",
            "response": "As an avid reader, I find that immersing myself in literature not only expands my vocabulary but also enhances my linguistic proficiency. The intricate narratives and sophisticated language structures provide invaluable insights into effective communication.",
            "expected_level": "C1-C2"
        }
    ]
    
    print("\n2. 测试不同水平的回答...")
    results = []
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n   --- 测试 {i}: {case['name']} ---")
        print(f"   回答: {case['response'][:50]}...")
        
        try:
            response = requests.post(
                f"{BASE_URL}/conversations/{conversation_id}/respond",
                json={"user_response": case['response']},
                timeout=90
            )
            assert response.status_code == 200
            data = response.json()
            assessment = data['assessment']
            profile = assessment['ability_profile']
            
            print(f"   ✅ 评估成功")
            print(f"      总分: {profile['overall_score']}/100")
            print(f"      CEFR等级: {profile['cefr_level']}")
            print(f"      强项: {', '.join(profile['strengths']) if profile['strengths'] else '无'}")
            print(f"      弱项: {', '.join(profile['weaknesses']) if profile['weaknesses'] else '无'}")
            print(f"      维度评分数: {len(assessment['dimension_scores'])}")
            
            # 显示维度评分
            for dim in assessment['dimension_scores'][:2]:  # 只显示前2个
                print(f"      - {dim['dimension']}: {dim['score']}/5")
            
            results.append({
                "name": case['name'],
                "score": profile['overall_score'],
                "level": profile['cefr_level'],
                "strengths": profile['strengths'],
                "weaknesses": profile['weaknesses']
            })
            
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 3. 总结
    print("\n" + "=" * 70)
    print(" 测试总结")
    print("=" * 70)
    
    if results:
        print("\n评估结果对比:")
        for r in results:
            print(f"  {r['name']}: {r['score']:.1f}分, {r['level']}级")
        
        # 检查是否有区分度
        scores = [r['score'] for r in results]
        if max(scores) - min(scores) > 10:
            print("\n✅ 评估系统有良好的区分度")
        else:
            print("\n⚠️  评估分数差异较小，可能需要优化")
        
        print("\n✅ 评估功能测试完成！")
        return True
    else:
        print("\n❌ 没有成功的测试结果")
        return False

if __name__ == "__main__":
    try:
        success = test_assessment()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试中断")
        exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)





