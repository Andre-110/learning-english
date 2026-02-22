#!/usr/bin/env python3
"""
测试分数与等级对齐功能 - 验证评估服务是否严格按照分数定级别
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
import time
from core.cefr_mapper import CEFRMapper
from models.user import CEFRLevel

BASE_URL = "http://localhost:8000"

def test_score_alignment():
    """测试分数与等级对齐"""
    print("=" * 70)
    print("测试分数与等级对齐功能")
    print("=" * 70)
    print()
    
    # 测试用例：不同分数的回答
    test_cases = [
        {
            "name": "低分回答（应该A1）",
            "response": "I student.",
            "expected_score_range": (0, 30),
            "expected_level": CEFRLevel.A1
        },
        {
            "name": "中低分回答（应该A2）",
            "response": "I am student. I like book.",
            "expected_score_range": (30, 50),
            "expected_level": CEFRLevel.A2
        },
        {
            "name": "中分回答（应该B1）",
            "response": "I am a student. I like reading books very much. Reading helps me learn new words.",
            "expected_score_range": (50, 75),
            "expected_level": CEFRLevel.B1
        },
        {
            "name": "高分回答（应该B2或C1）",
            "response": "As an avid reader, I find that immersing myself in literature not only expands my vocabulary but also enhances my linguistic proficiency. The intricate narratives and sophisticated language structures provide invaluable insights into effective communication.",
            "expected_score_range": (70, 100),
            "expected_level": None  # 可能是B2或C1
        }
    ]
    
    # 开始对话
    print("1. 开始对话...")
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "alignment_test"},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        conversation_id = data["conversation_id"]
        print(f"   ✅ 对话已开始: {conversation_id}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        return False
    
    print()
    print("2. 测试不同分数的等级映射...")
    print("-" * 70)
    
    results = []
    all_aligned = True
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {case['name']}")
        print(f"回答: {case['response'][:60]}...")
        
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
            score = profile['overall_score']
            level_str = profile['cefr_level']
            
            # 根据分数映射期望的等级
            expected_level = CEFRMapper.score_to_cefr(score)
            actual_level = CEFRLevel(level_str)
            
            # 检查是否对齐
            is_aligned = (actual_level == expected_level)
            
            if not is_aligned:
                all_aligned = False
            
            status = "✅" if is_aligned else "❌"
            
            print(f"   {status} 分数: {score:.1f}/100")
            print(f"      实际等级: {actual_level.value}")
            print(f"      期望等级: {expected_level.value}")
            print(f"      对齐状态: {'✅ 对齐' if is_aligned else '❌ 未对齐'}")
            
            if not is_aligned:
                print(f"      ⚠️  警告: 分数{score:.1f}应该对应{expected_level.value}，但返回了{actual_level.value}")
            
            results.append({
                "case": case['name'],
                "score": score,
                "actual_level": actual_level.value,
                "expected_level": expected_level.value,
                "aligned": is_aligned
            })
            
            time.sleep(1)
            
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 总结
    print()
    print("=" * 70)
    print("测试总结")
    print("=" * 70)
    
    aligned_count = sum(1 for r in results if r['aligned'])
    total_count = len(results)
    
    print(f"\n对齐情况: {aligned_count}/{total_count}")
    
    for r in results:
        status = "✅" if r['aligned'] else "❌"
        print(f"{status} {r['case']}: {r['score']:.1f}分 -> {r['actual_level']} (期望: {r['expected_level']})")
    
    if all_aligned:
        print("\n✅ 所有测试通过！分数与等级完全对齐。")
    else:
        print("\n❌ 部分测试失败！存在分数与等级不对齐的情况。")
        print("   请检查评估服务是否正确使用了CEFR映射器。")
    
    return all_aligned

if __name__ == "__main__":
    try:
        success = test_score_alignment()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试中断")
        exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)





