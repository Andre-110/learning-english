#!/usr/bin/env python3
"""
验证分数与等级对齐功能
"""
import requests
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cefr_mapper import CEFRMapper
from models.user import CEFRLevel

BASE_URL = "http://localhost:8000"

def verify_alignment():
    """验证分数与等级对齐"""
    print("=" * 70)
    print("验证分数与等级对齐功能")
    print("=" * 70)
    print()
    
    # 开始对话
    print("1. 开始对话...")
    try:
        resp = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "alignment_verify"},
            timeout=30
        )
        conv_id = resp.json()["conversation_id"]
        print(f"   ✅ 对话ID: {conv_id}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        return False
    
    # 测试多个不同分数的回答
    test_cases = [
        {
            "name": "低分回答",
            "response": "I student.",
            "expected_range": (0, 30)
        },
        {
            "name": "中低分回答",
            "response": "I am student. I like book.",
            "expected_range": (30, 50)
        },
        {
            "name": "中分回答（75分）",
            "response": "I am a student. I like reading books very much. Reading helps me learn new words and improve my English skills. I read for about 30 minutes every day.",
            "expected_range": (50, 75)
        },
        {
            "name": "高分回答",
            "response": "As an avid reader, I find that immersing myself in literature not only expands my vocabulary but also enhances my linguistic proficiency. The intricate narratives and sophisticated language structures provide invaluable insights into effective communication.",
            "expected_range": (70, 100)
        }
    ]
    
    print()
    print("2. 测试不同分数的等级映射...")
    print("-" * 70)
    
    all_aligned = True
    results = []
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {case['name']}")
        
        try:
            resp = requests.post(
                f"{BASE_URL}/conversations/{conv_id}/respond",
                json={"user_response": case["response"]},
                timeout=90
            )
            
            data = resp.json()
            assessment = data["assessment"]
            profile = assessment["ability_profile"]
            score = profile["overall_score"]
            level_str = profile["cefr_level"]
            
            # 根据分数映射期望等级
            expected_level = CEFRMapper.score_to_cefr(score)
            actual_level = CEFRLevel(level_str)
            
            is_aligned = (actual_level == expected_level)
            if not is_aligned:
                all_aligned = False
            
            status = "✅" if is_aligned else "❌"
            
            print(f"   {status} 分数: {score:.1f}/100")
            print(f"      实际等级: {actual_level.value}")
            print(f"      期望等级: {expected_level.value}")
            
            if not is_aligned:
                print(f"      ⚠️  未对齐！分数{score:.1f}应该对应{expected_level.value}")
            
            results.append({
                "case": case["name"],
                "score": score,
                "actual": actual_level.value,
                "expected": expected_level.value,
                "aligned": is_aligned
            })
            
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 总结
    print()
    print("=" * 70)
    print("验证总结")
    print("=" * 70)
    
    aligned_count = sum(1 for r in results if r["aligned"])
    total_count = len(results)
    
    print(f"\n对齐情况: {aligned_count}/{total_count}")
    print()
    
    for r in results:
        status = "✅" if r["aligned"] else "❌"
        print(f"{status} {r['case']}: {r['score']:.1f}分 -> {r['actual']} (期望: {r['expected']})")
    
    print()
    if all_aligned:
        print("✅ 所有测试通过！分数与等级完全对齐。")
        print("✅ 系统严格按照分数来定级别！")
    else:
        print("❌ 部分测试失败！存在分数与等级不对齐的情况。")
    
    return all_aligned

if __name__ == "__main__":
    try:
        success = verify_alignment()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)





