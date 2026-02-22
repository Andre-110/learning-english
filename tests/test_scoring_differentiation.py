#!/usr/bin/env python3
"""
测试评分区分度 - 验证不同质量的输入是否得到不同的分数
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.qwen_omni_audio import QwenOmniAudioService
from prompts.templates import get_system_prompt, get_user_prompt_for_text
import json

# 测试用例：不同质量的输入
TEST_CASES = [
    # A1 级别
    {
        "id": 1,
        "input": "Hello. Yes. Good.",
        "expected_level": "A1",
        "expected_score_range": (15, 25),
        "reason": "只有单词，没有句子结构"
    },
    # A2 级别
    {
        "id": 2,
        "input": "Hello! I want to talk about football.",
        "expected_level": "A2",
        "expected_score_range": (30, 45),
        "reason": "简单句，基础词汇"
    },
    # B1 级别
    {
        "id": 3,
        "input": "Can you tell me more about his early career?",
        "expected_level": "B1",
        "expected_score_range": (45, 60),
        "reason": "复杂疑问句，good vocabulary"
    },
    # B2 级别
    {
        "id": 4,
        "input": "Although Messi faced many challenges in his early career, he never gave up and eventually became one of the greatest players.",
        "expected_level": "B2",
        "expected_score_range": (60, 75),
        "reason": "复杂句式，从句，高级词汇"
    },
    # C1 级别
    {
        "id": 5,
        "input": "The proliferation of artificial intelligence has precipitated a paradigm shift in how we conceptualize human-machine interaction.",
        "expected_level": "C1",
        "expected_score_range": (80, 92),
        "reason": "高级词汇 (proliferation, precipitated, paradigm)，复杂结构"
    },
    # C2 级别
    {
        "id": 6,
        "input": "The epistemological underpinnings of contemporary discourse reveal a fascinating interplay between Cartesian dualism and emergent materialism.",
        "expected_level": "C2",
        "expected_score_range": (92, 100),
        "reason": "学术级词汇 (epistemological, underpinnings, Cartesian dualism)，哲学深度"
    },
    # 语法错误
    {
        "id": 7,
        "input": "Can you explain can you tell me more about his career",
        "expected_level": "A1-A2",
        "expected_score_range": (20, 35),
        "reason": "严重语法错误（重复结构）"
    },
    {
        "id": 8,
        "input": "I want to know more about can you tell me more about his legacy",
        "expected_level": "A1-A2",
        "expected_score_range": (20, 35),
        "reason": "严重语法错误（句子结构混乱）"
    }
]

def test_scoring():
    """测试评分区分度"""
    service = QwenOmniAudioService()
    
    results = []
    
    for case in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"测试 #{case['id']}: {case['input'][:50]}...")
        print(f"预期: {case['expected_level']}, 分数范围: {case['expected_score_range']}")
        print(f"原因: {case['reason']}")
        
        # 构建消息
        system_prompt = get_system_prompt()
        user_prompt = get_user_prompt_for_text(case['input'])
        
        try:
            # 调用 API (使用 call_with_text)
            response_text = service.call_with_text(system_prompt, user_prompt)
            
            # 解析 JSON 结果
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                response = json.loads(json_match.group())
            else:
                print(f"❌ 无法解析 JSON: {response_text[:100]}")
                continue
            
            # 解析结果
            if isinstance(response, dict):
                score = response.get("evaluation", {}).get("overall_score", 0)
                level = response.get("evaluation", {}).get("cefr_level", "?")
                
                min_score, max_score = case['expected_score_range']
                in_range = min_score <= score <= max_score
                
                print(f"✅ 实际评分: {score} ({level})")
                print(f"{'✅ 在预期范围内' if in_range else '❌ 超出预期范围'}")
                
                results.append({
                    "id": case['id'],
                    "input": case['input'],
                    "expected_range": case['expected_score_range'],
                    "actual_score": score,
                    "actual_level": level,
                    "in_range": in_range
                })
            else:
                print(f"❌ 错误: {response}")
                
        except Exception as e:
            print(f"❌ 异常: {e}")
    
    # 总结
    print(f"\n{'='*60}")
    print("📊 评分区分度分析")
    print(f"{'='*60}")
    
    scores = [r["actual_score"] for r in results if "actual_score" in r]
    if scores:
        print(f"分数范围: {min(scores)} - {max(scores)}")
        print(f"分数差异: {max(scores) - min(scores)}")
        
        in_range_count = sum(1 for r in results if r.get("in_range", False))
        print(f"符合预期: {in_range_count}/{len(results)}")
        
        if max(scores) - min(scores) < 15:
            print("⚠️ 警告: 评分区分度不足！不同质量的输入分数差异应该 > 15分")
        else:
            print("✅ 评分区分度良好")
    
    return results

if __name__ == "__main__":
    results = test_scoring()
    
    # 保存结果
    with open("scoring_differentiation_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("\n结果已保存到 scoring_differentiation_results.json")

