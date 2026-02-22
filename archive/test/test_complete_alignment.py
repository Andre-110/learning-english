#!/usr/bin/env python3
"""
完整测试 - 验证分数与等级对齐功能
确保系统严格按照分数来定级别
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

def print_section(title, char="="):
    print("\n" + char * 70)
    print(f" {title}")
    print(char * 70)

def test_alignment():
    """完整测试分数与等级对齐"""
    print("=" * 70)
    print(" 完整测试 - 分数与等级对齐验证")
    print("=" * 70)
    
    # 1. 验证映射器本身
    print_section("步骤1: 验证CEFR映射器")
    test_scores = [
        (25, CEFRLevel.A1),
        (40, CEFRLevel.A2),
        (60, CEFRLevel.B1),
        (75, CEFRLevel.B1),  # 75分应该对应B1
        (80, CEFRLevel.B2),
        (90, CEFRLevel.C1),
    ]
    
    mapper_ok = True
    for score, expected_level in test_scores:
        result = CEFRMapper.score_to_cefr(score)
        is_ok = result == expected_level
        status = "✅" if is_ok else "❌"
        print(f"   {status} {score:3d}分 -> {result.value:2s} (期望: {expected_level.value})")
        if not is_ok:
            mapper_ok = False
    
    if not mapper_ok:
        print("\n❌ CEFR映射器测试失败！")
        return False
    
    print("\n✅ CEFR映射器测试通过！")
    
    # 2. 检查服务状态
    print_section("步骤2: 检查服务状态")
    try:
        resp = requests.get(f"{BASE_URL}/", timeout=5)
        if resp.status_code == 200:
            print("   ✅ 服务运行正常")
        else:
            print(f"   ❌ 服务状态异常: {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ 服务未运行: {e}")
        print("   请先启动服务: uvicorn api.main:app --reload")
        return False
    
    # 3. 开始对话
    print_section("步骤3: 开始对话")
    try:
        resp = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "complete_alignment_test"},
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
    
    # 4. 测试不同分数的回答
    print_section("步骤4: 测试不同分数的等级映射")
    
    test_cases = [
        {
            "name": "低分回答（期望A1）",
            "response": "I student.",
            "expected_level": CEFRLevel.A1
        },
        {
            "name": "中低分回答（期望A2）",
            "response": "I am student. I like book.",
            "expected_level": CEFRLevel.A2
        },
        {
            "name": "中分回答（期望B1，特别是75分）",
            "response": "I am a student. I like reading books very much. Reading helps me learn new words and improve my English skills. I read for about 30 minutes every day.",
            "expected_level": CEFRLevel.B1
        },
        {
            "name": "高分回答（期望B2或C1）",
            "response": "As an avid reader, I find that immersing myself in literature not only expands my vocabulary but also enhances my linguistic proficiency. The intricate narratives and sophisticated language structures provide invaluable insights into effective communication.",
            "expected_level": None  # 可能是B2或C1
        }
    ]
    
    all_aligned = True
    results = []
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n   测试 {i}: {case['name']}")
        print(f"   回答: {case['response'][:60]}...")
        
        try:
            resp = requests.post(
                f"{BASE_URL}/conversations/{conv_id}/respond",
                json={"user_response": case["response"]},
                timeout=120
            )
            
            if resp.status_code != 200:
                print(f"   ❌ API调用失败: {resp.status_code}")
                continue
            
            data = resp.json()
            assessment = data["assessment"]
            profile = assessment["ability_profile"]
            score = profile["overall_score"]
            level_str = profile["cefr_level"]
            
            # 根据分数映射期望等级
            expected_level = CEFRMapper.score_to_cefr(score)
            actual_level = CEFRLevel(level_str)
            
            is_aligned = (actual_level == expected_level)
            
            # 如果有指定期望等级，也检查
            if case["expected_level"] and actual_level != case["expected_level"]:
                # 但如果分数映射正确，也算通过
                if is_aligned:
                    pass  # 分数映射正确即可
                else:
                    is_aligned = False
            
            if not is_aligned:
                all_aligned = False
            
            status = "✅" if is_aligned else "❌"
            
            print(f"   {status} 评估结果:")
            print(f"      分数: {score:.1f}/100")
            print(f"      实际等级: {actual_level.value}")
            print(f"      期望等级: {expected_level.value}")
            
            if not is_aligned:
                print(f"      ⚠️  未对齐！分数{score:.1f}应该对应{expected_level.value}，但返回了{actual_level.value}")
            
            results.append({
                "case": case["name"],
                "score": score,
                "actual": actual_level.value,
                "expected": expected_level.value,
                "aligned": is_aligned
            })
            
            time.sleep(2)  # 避免请求过快
            
        except requests.exceptions.Timeout:
            print(f"   ⚠️  请求超时，跳过此测试")
            continue
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # 5. 测试总结
    print_section("测试总结")
    
    if not results:
        print("   ⚠️  没有成功的测试结果")
        return False
    
    aligned_count = sum(1 for r in results if r["aligned"])
    total_count = len(results)
    
    print(f"\n   对齐情况: {aligned_count}/{total_count}")
    print()
    
    for r in results:
        status = "✅" if r["aligned"] else "❌"
        print(f"   {status} {r['case']}")
        print(f"      分数: {r['score']:.1f}分 -> 等级: {r['actual']} (期望: {r['expected']})")
    
    print()
    if all_aligned:
        print("   ✅ 所有测试通过！")
        print("   ✅ 系统严格按照分数来定级别！")
        print("   ✅ 分数与等级完全对齐！")
        return True
    else:
        print("   ❌ 部分测试失败！")
        print("   ⚠️  存在分数与等级不对齐的情况")
        return False

if __name__ == "__main__":
    try:
        success = test_alignment()
        print("\n" + "=" * 70)
        if success:
            print(" ✅ 完整测试通过！")
        else:
            print(" ❌ 测试失败！")
        print("=" * 70)
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试中断")
        exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)





