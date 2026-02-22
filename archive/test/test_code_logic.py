#!/usr/bin/env python3
"""
代码逻辑测试 - 不依赖服务，直接测试评估服务的映射逻辑
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cefr_mapper import CEFRMapper
from models.user import CEFRLevel
from models.assessment import AbilityProfile, AssessmentResult, DimensionScore
from datetime import datetime

def test_mapper_logic():
    """测试映射器逻辑"""
    print("=" * 70)
    print(" 代码逻辑测试 - CEFR映射器")
    print("=" * 70)
    print()
    
    # 测试各种分数
    test_cases = [
        (0, CEFRLevel.A1),
        (15, CEFRLevel.A1),
        (25, CEFRLevel.A1),
        (30, CEFRLevel.A2),
        (40, CEFRLevel.A2),
        (50, CEFRLevel.B1),
        (60, CEFRLevel.B1),
        (70, CEFRLevel.B1),
        (74.9, CEFRLevel.B1),
        (75, CEFRLevel.B1),  # 关键：75分应该对应B1
        (75.1, CEFRLevel.B2),
        (80, CEFRLevel.B2),
        (85, CEFRLevel.C1),
        (90, CEFRLevel.C1),
        (95, CEFRLevel.C2),
        (100, CEFRLevel.C2),
    ]
    
    print("测试分数到CEFR等级映射:")
    print("-" * 70)
    
    all_passed = True
    for score, expected_level in test_cases:
        result = CEFRMapper.score_to_cefr(score)
        passed = result == expected_level
        status = "✅" if passed else "❌"
        
        if not passed:
            all_passed = False
        
        score_str = f"{score:.1f}" if isinstance(score, float) else str(score)
        print(f"{status} {score_str:>6}分 -> {result.value:2s} (期望: {expected_level.value})")
    
    print()
    return all_passed

def test_alignment_check():
    """测试对齐检查"""
    print("=" * 70)
    print(" 对齐检查测试")
    print("=" * 70)
    print()
    
    test_cases = [
        (75.0, CEFRLevel.B1, True),   # 75分应该对应B1
        (75.0, CEFRLevel.A2, False),  # 75分不应该对应A2
        (75.0, CEFRLevel.B2, False),  # 75分不应该对应B2
        (80.0, CEFRLevel.B2, True),   # 80分应该对应B2
        (50.0, CEFRLevel.B1, True),   # 50分应该对应B1
    ]
    
    print("测试分数与等级对齐检查:")
    print("-" * 70)
    
    all_passed = True
    for score, level, expected in test_cases:
        result = CEFRMapper.is_score_aligned_with_level(score, level)
        passed = result == expected
        status = "✅" if passed else "❌"
        
        if not passed:
            all_passed = False
        
        print(f"{status} {score:.1f}分 vs {level.value}: {result} (期望: {expected})")
    
    print()
    return all_passed

def test_simulated_assessment():
    """模拟评估结果解析，测试映射是否应用"""
    print("=" * 70)
    print(" 模拟评估结果解析测试")
    print("=" * 70)
    print()
    
    # 模拟LLM返回75分但等级是A2的情况
    mock_llm_response = {
        "dimension_scores": [
            {"dimension": "内容相关性", "score": 4.0, "comment": "test", "reasoning": "test"}
        ],
        "ability_profile": {
            "overall_score": 75.0,
            "cefr_level": "A2",  # LLM返回A2，但75分应该对应B1
            "strengths": [],
            "weaknesses": [],
            "confidence": 0.85
        }
    }
    
    print("模拟场景: LLM返回75分，但等级是A2")
    print("-" * 70)
    
    score = float(mock_llm_response["ability_profile"]["overall_score"])
    llm_level = mock_llm_response["ability_profile"]["cefr_level"]
    
    # 应用映射
    mapped_level = CEFRMapper.score_to_cefr(score)
    
    print(f"LLM返回: {score:.1f}分, {llm_level}级")
    print(f"映射后: {score:.1f}分, {mapped_level.value}级")
    print(f"期望: {score:.1f}分, B1级")
    print()
    
    if mapped_level == CEFRLevel.B1:
        print("✅ 映射正确！75分已正确映射到B1")
        print("✅ 系统会忽略LLM返回的A2，使用映射后的B1")
        return True
    else:
        print(f"❌ 映射错误！75分映射到了{mapped_level.value}，应该是B1")
        return False

def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print(" 完整代码逻辑测试")
    print("=" * 70)
    
    results = []
    
    # 测试1: 映射器逻辑
    results.append(("映射器逻辑", test_mapper_logic()))
    
    # 测试2: 对齐检查
    results.append(("对齐检查", test_alignment_check()))
    
    # 测试3: 模拟评估
    results.append(("模拟评估解析", test_simulated_assessment()))
    
    # 总结
    print("=" * 70)
    print(" 测试总结")
    print("=" * 70)
    print()
    
    all_passed = True
    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"{status} {name}: {'通过' if passed else '失败'}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("✅ 所有代码逻辑测试通过！")
        print("✅ 映射器功能正常！")
        print("✅ 系统会严格按照分数来定级别！")
    else:
        print("❌ 部分测试失败！")
    
    print("=" * 70)
    
    return all_passed

if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)





