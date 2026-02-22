#!/usr/bin/env python3
"""
测试 qwen3-omni-flash 模型的评分区分度
使用 get_user_prompt_for_audio() 的评分标准
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.qwen_omni_audio import QwenOmniAudioService
from prompts.templates import get_system_prompt, get_user_prompt_for_audio
import json
import re

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
        "expected_score_range": (60, 80),
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
]

def test_scoring():
    """测试评分区分度"""
    service = QwenOmniAudioService()
    
    results = []
    
    # 使用音频处理的 prompt（这是 qwen3-omni 实际使用的）
    system_prompt = get_system_prompt()
    audio_prompt = get_user_prompt_for_audio()
    
    for case in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"测试 #{case['id']}: {case['input'][:50]}...")
        print(f"预期: {case['expected_level']}, 分数范围: {case['expected_score_range']}")
        print(f"原因: {case['reason']}")
        
        # 模拟音频转录后的文本处理
        # 在实际使用中，音频会被转录，然后用这个 prompt 处理
        user_content = f"""[Simulated transcription for testing]
The user said: "{case['input']}"

{audio_prompt}"""
        
        try:
            # 使用 qwen3-omni-flash 模型（音频模型）
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            # 调用流式 API
            full_response = ""
            for chunk in service.call_with_text_stream(system_prompt, user_content):
                full_response += chunk
            
            # 解析 JSON 结果
            json_match = re.search(r'\{[\s\S]*\}', full_response)
            if json_match:
                response = json.loads(json_match.group())
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
                    "expected_level": case['expected_level'],
                    "actual_score": score,
                    "actual_level": level,
                    "in_range": in_range
                })
            else:
                print(f"❌ 无法解析 JSON: {full_response[:200]}")
                
        except Exception as e:
            print(f"❌ 异常: {e}")
    
    # 总结
    print(f"\n{'='*60}")
    print("📊 qwen3-omni-flash 评分区分度分析")
    print(f"{'='*60}")
    
    scores = [r["actual_score"] for r in results if "actual_score" in r]
    if scores:
        print(f"分数范围: {min(scores)} - {max(scores)}")
        print(f"分数差异: {max(scores) - min(scores)}")
        
        in_range_count = sum(1 for r in results if r.get("in_range", False))
        print(f"符合预期: {in_range_count}/{len(results)}")
        
        print("\n详细结果:")
        for r in results:
            status = "✅" if r.get("in_range") else "❌"
            print(f"  {status} #{r['id']}: {r['actual_score']}分 ({r['actual_level']}) - 预期 {r['expected_range']}")
        
        if max(scores) - min(scores) < 30:
            print("\n⚠️ 警告: 评分区分度不足！")
        else:
            print("\n✅ 评分区分度良好")
    
    return results

if __name__ == "__main__":
    results = test_scoring()
    
    # 保存结果
    with open("qwen_omni_scoring_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("\n结果已保存到 qwen_omni_scoring_results.json")

