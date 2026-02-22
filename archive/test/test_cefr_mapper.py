#!/usr/bin/env python3
"""
测试CEFR等级映射器
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cefr_mapper import CEFRMapper
from models.user import CEFRLevel

def test_score_to_cefr():
    """测试分数到CEFR等级映射"""
    print("=" * 70)
    print("测试CEFR等级映射器")
    print("=" * 70)
    print()
    
    test_cases = [
        (0, CEFRLevel.A1),
        (15, CEFRLevel.A1),
        (30, CEFRLevel.A2),
        (40, CEFRLevel.A2),
        (50, CEFRLevel.B1),
        (60, CEFRLevel.B1),
        (70, CEFRLevel.B1),  # 70分属于B1范围（50-75）
        (74.9, CEFRLevel.B1),  # 74.9分属于B1
        (75, CEFRLevel.B1),  # 75分属于B1（包含75）
        (75.1, CEFRLevel.B2),  # 75.1分属于B2
        (80, CEFRLevel.B2),
        (85, CEFRLevel.C1),
        (90, CEFRLevel.C1),
        (95, CEFRLevel.C2),
        (100, CEFRLevel.C2),
    ]
    
    print("分数 -> CEFR等级映射:")
    print("-" * 70)
    all_passed = True
    
    for score, expected_level in test_cases:
        result = CEFRMapper.score_to_cefr(score)
        passed = result == expected_level
        status = "✅" if passed else "❌"
        
        if not passed:
            all_passed = False
        
        # 格式化分数显示
        if isinstance(score, float) and score % 1 != 0:
            score_str = f"{score:.1f}"
        else:
            score_str = f"{int(score)}"
        
        print(f"{status} {score_str:>5}分 -> {result.value:2s} (期望: {expected_level.value})")
    
    print()
    print("=" * 70)
    
    if all_passed:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败")
    
    return all_passed

def test_score_ranges():
    """测试分数范围"""
    print("\n" + "=" * 70)
    print("CEFR等级分数范围:")
    print("=" * 70)
    
    for level in [CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1, CEFRLevel.B2, CEFRLevel.C1, CEFRLevel.C2]:
        min_score, max_score = CEFRMapper.get_score_range(level)
        # 格式化分数显示
        if isinstance(max_score, float):
            max_str = f"{max_score:.1f}"
        else:
            max_str = f"{int(max_score)}"
        if isinstance(min_score, float):
            min_str = f"{min_score:.1f}"
        else:
            min_str = f"{int(min_score)}"
        print(f"{level.value:2s}: {min_str:>4} - {max_str:>4}分")
    
    print()

def test_alignment():
    """测试分数与等级对齐"""
    print("\n" + "=" * 70)
    print("测试分数与等级对齐:")
    print("=" * 70)
    
    test_cases = [
        (75.0, CEFRLevel.B1, True),   # 75分应该对应B1（包含75）
        (74.9, CEFRLevel.B1, True),   # 74.9分应该对应B1
        (75.1, CEFRLevel.B2, True),   # 75.1分应该对应B2
        (75.0, CEFRLevel.A2, False),  # 75分不应该对应A2
        (75.0, CEFRLevel.B2, False),  # 75分不应该对应B2（75属于B1）
        (85.0, CEFRLevel.C1, True),   # 85分应该对应C1
        (30.0, CEFRLevel.A2, True),   # 30分应该对应A2
    ]
    
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

if __name__ == "__main__":
    try:
        test1 = test_score_to_cefr()
        test_score_ranges()
        test2 = test_alignment()
        
        if test1 and test2:
            print("=" * 70)
            print("✅ 所有测试通过！")
            exit(0)
        else:
            print("=" * 70)
            print("❌ 部分测试失败")
            exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

