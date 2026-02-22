#!/usr/bin/env python3
"""
语义完整性检测测试用例
测试真实口语场景中的不完整句子
"""
import asyncio
import sys
sys.path.insert(0, '/home/ubuntu/learning_english')

from dotenv import load_dotenv
load_dotenv('/home/ubuntu/learning_english/.env')

from services.semantic_completeness import get_semantic_checker

# 测试用例：括号前的部分都应该是不完整的
TEST_CASES = [
    # (句子片段, 期望是否完整, 说明)
    ("I think the most important thing in life is", False, "缺少 is 后面的补语"),
    ("Well you know", False, "口语开头，未完成"),
    ("I actually", False, "缺少动作"),
    ("My daily routine is", False, "缺少 is 后面的内容"),
    ("I'm interested in", False, "缺少 in 后面的宾语"),
    ("oh what's that word", False, "在想词，未完成"),
    ("If I had a million dollars I would", False, "条件句未完成"),
    ("I feel a bit", False, "缺少形容词"),
    ("My dream job is to be a", False, "缺少职业名称"),
    ("I used to live in London sorry I mean", False, "在纠正，未完成"),
    ("The weather in my city is", False, "缺少描述"),
    ("To be honest", False, "引导语，未说正题"),
    
    # 完整句子测试
    ("My daily routine", True, "名词短语作为回答"),
    ("I love jazz", True, "完整句子"),
    ("waking up at 7 am", True, "动名词短语作为回答"),
    ("architecture", True, "单词回答"),
    ("buy a big house", True, "动词短语作为回答"),
    ("lonely sometimes but it's okay", True, "完整表达"),
    ("a director", True, "名词回答"),
    ("Manchester", True, "地名回答"),
    ("quite humid", True, "形容词短语回答"),
    ("I haven't thought about it yet", True, "完整句子"),
    ("to be happy", True, "不定式短语作为回答"),
]

async def run_tests():
    checker = get_semantic_checker()
    
    print("=" * 70)
    print("语义完整性检测测试")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for text, expected_complete, description in TEST_CASES:
        is_complete, confidence, reason = await checker.check_async(text)
        
        status = "✅" if is_complete == expected_complete else "❌"
        if is_complete == expected_complete:
            passed += 1
        else:
            failed += 1
        
        expected_str = "完整" if expected_complete else "不完整"
        actual_str = "完整" if is_complete else "不完整"
        
        print(f"\n{status} 「{text}」")
        print(f"   期望: {expected_str} | 实际: {actual_str} (置信度: {confidence:.2f})")
        print(f"   原因: {reason}")
        print(f"   说明: {description}")
    
    print("\n" + "=" * 70)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 70)
    
    return failed == 0

if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
