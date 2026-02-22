"""
提取并展示 qwen-omni 模型输出的建议（仅展示给前端的内容）
"""
import json

# 读取测试结果
with open('qwen_omni_test_results.json', 'r', encoding='utf-8') as f:
    results = json.load(f)

print("=" * 100)
print("qwen-omni 模型输出的建议（展示给前端）")
print("=" * 100)
print()

for i, result in enumerate(results, 1):
    if 'error' in result:
        continue
    
    input_text = result['input']
    suggestions = result['suggestions']
    
    print(f"\n{'='*100}")
    print(f"用例 {i}/20: {input_text}")
    print(f"{'='*100}")
    
    # 评估结果
    print(f"\n📊 评估: {suggestions['score']}分 ({suggestions['level']})")
    
    # 修正建议（最重要的部分）
    corrections = suggestions['corrections']
    if corrections:
        print(f"\n✏️  修正建议 ({len(corrections)}条):")
        for j, correction in enumerate(corrections, 1):
            if isinstance(correction, dict):
                original = correction.get('original', '')
                corrected = correction.get('corrected', '')
                explanation = correction.get('explanation', '')
                print(f"  {j}. {original} → {corrected}")
                if explanation:
                    print(f"     说明: {explanation}")
            else:
                print(f"  {j}. {correction}")
    else:
        print("\n✏️  修正建议: (无)")
    
    # 强项
    if suggestions['strengths']:
        print(f"\n✅ 强项: {', '.join(suggestions['strengths'])}")
    
    # 弱项
    if suggestions['weaknesses']:
        print(f"\n⚠️  弱项: {', '.join(suggestions['weaknesses'])}")
    
    # 好的表达
    if suggestions['good_expressions']:
        print(f"\n🌟 好的表达: {', '.join(suggestions['good_expressions'])}")
    
    # 鼓励语
    print(f"\n💬 鼓励语: {suggestions['encouragement']}")

# 统计摘要
print("\n" + "=" * 100)
print("📈 统计摘要")
print("=" * 100)

successful = [r for r in results if 'suggestions' in r]
print(f"\n成功处理: {len(successful)}/20")

if successful:
    scores = [r['suggestions']['score'] for r in successful]
    avg_score = sum(scores) / len(scores)
    print(f"平均分数: {avg_score:.1f}")
    
    total_corrections = sum(len(r['suggestions']['corrections']) for r in successful)
    cases_with_corrections = sum(1 for r in successful if r['suggestions']['corrections'])
    
    print(f"\n修正建议统计:")
    print(f"  总修正数: {total_corrections}")
    print(f"  有修正的用例: {cases_with_corrections}/{len(successful)}")
    print(f"  平均每用例修正数: {total_corrections/len(successful):.1f}")

print("\n" + "=" * 100)


