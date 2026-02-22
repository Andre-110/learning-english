"""
展示 qwen-omni 模型输出的建议
从测试结果中提取并格式化展示
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
        print(f"\n用例 {i}: ❌ 错误 - {result['error']}")
        continue
    
    input_text = result['input']
    suggestions = result['suggestions']
    
    print(f"\n{'='*100}")
    print(f"用例 {i}/20")
    print(f"{'='*100}")
    print(f"📝 用户输入: {input_text}")
    print()
    
    # 判断输入类型
    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in input_text)
    has_english = any(char.isalpha() and ord(char) < 128 for char in input_text)
    
    if has_chinese and has_english:
        input_type = "中英文混杂"
    elif has_chinese:
        input_type = "纯中文"
    else:
        input_type = "纯英文"
    
    print(f"📌 输入类型: {input_type}")
    print()
    
    # 评估结果
    print("📊 评估结果:")
    print(f"  分数: {suggestions['score']} (等级: {suggestions['level']})")
    
    # 检查是否符合预期
    if input_type == "纯中文" and suggestions['score'] > 25:
        print(f"  ⚠️  问题: 纯中文输入应该给低分(10-25)，但给了 {suggestions['score']} 分")
    elif input_type == "中英文混杂" and suggestions['score'] > 40:
        print(f"  ⚠️  问题: 中英文混杂应该给较低分(25-40)，但给了 {suggestions['score']} 分")
    
    print()
    
    # 强项
    print("✅ 强项:")
    if suggestions['strengths']:
        for strength in suggestions['strengths']:
            print(f"  • {strength}")
    else:
        print("  (无)")
    print()
    
    # 弱项
    print("⚠️  弱项:")
    if suggestions['weaknesses']:
        for weakness in suggestions['weaknesses']:
            print(f"  • {weakness}")
    else:
        print("  (无)")
    print()
    
    # 修正建议（最重要的部分）
    print("✏️  修正建议:")
    corrections = suggestions['corrections']
    if corrections:
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
        print("  (无修正)")
        # 检查是否有明显错误但没有修正
        if input_type != "纯中文":
            if "play for" in input_text.lower() and "prefer" not in input_text.lower():
                print(f"     ⚠️  问题: 'play for' 可能是 'prefer' 的错误，但未给出修正")
            if "tell" in input_text.lower() and "talk" not in input_text.lower() and "tell" in input_text.split():
                print(f"     ⚠️  问题: 'tell' 可能是 'talk about' 的错误，但未给出修正")
            if "go" in input_text.lower() and "went" not in input_text.lower() and "yesterday" in input_text.lower():
                print(f"     ⚠️  问题: 过去时错误可能未修正")
    print()
    
    # 好的表达
    print("🌟 好的表达:")
    if suggestions['good_expressions']:
        for expr in suggestions['good_expressions']:
            print(f"  • {expr}")
    else:
        print("  (无)")
    print()
    
    # 鼓励语
    print("💬 鼓励语:")
    print(f"  {suggestions['encouragement']}")
    print()

# 统计摘要
print("\n" + "=" * 100)
print("📈 统计摘要")
print("=" * 100)

successful = [r for r in results if 'suggestions' in r]
print(f"\n成功处理: {len(successful)}/20")

if successful:
    # 按输入类型分类
    pure_chinese = [r for r in successful if any('\u4e00' <= char <= '\u9fff' for char in r['input']) and not any(char.isalpha() and ord(char) < 128 for char in r['input'])]
    mixed = [r for r in successful if any('\u4e00' <= char <= '\u9fff' for char in r['input']) and any(char.isalpha() and ord(char) < 128 for char in r['input'])]
    pure_english = [r for r in successful if not any('\u4e00' <= char <= '\u9fff' for char in r['input'])]
    
    print(f"\n输入类型分布:")
    print(f"  纯中文: {len(pure_chinese)} 个")
    print(f"  中英文混杂: {len(mixed)} 个")
    print(f"  纯英文: {len(pure_english)} 个")
    
    # 分数统计
    scores = [r['suggestions']['score'] for r in successful]
    avg_score = sum(scores) / len(scores)
    print(f"\n分数统计:")
    print(f"  平均分数: {avg_score:.1f}")
    print(f"  最高分: {max(scores)}")
    print(f"  最低分: {min(scores)}")
    
    # 纯中文输入的分数
    if pure_chinese:
        chinese_scores = [r['suggestions']['score'] for r in pure_chinese]
        avg_chinese = sum(chinese_scores) / len(chinese_scores)
        print(f"\n纯中文输入分数:")
        print(f"  平均: {avg_chinese:.1f} (预期: 10-25)")
        if avg_chinese > 25:
            print(f"  ⚠️  问题: 纯中文输入分数过高，应该给低分")
    
    # 修正统计
    total_corrections = sum(len(r['suggestions']['corrections']) for r in successful)
    cases_with_corrections = sum(1 for r in successful if r['suggestions']['corrections'])
    cases_without_corrections = len(successful) - cases_with_corrections
    
    print(f"\n修正建议统计:")
    print(f"  总修正数: {total_corrections}")
    print(f"  有修正的用例: {cases_with_corrections}/{len(successful)}")
    print(f"  无修正的用例: {cases_without_corrections}/{len(successful)}")
    
    # 检查明显错误但未修正的情况
    print(f"\n⚠️  潜在问题:")
    issues = []
    for r in successful:
        input_text = r['input'].lower()
        corrections = r['suggestions']['corrections']
        
        # 检查 "play for" 错误
        if "play for" in input_text and "prefer" not in input_text and not corrections:
            issues.append(f"  • '{r['input']}' - 'play for' 可能是 'prefer' 的错误，但未修正")
        
        # 检查 "tell" vs "talk about"
        if "tell" in input_text.split() and "talk" not in input_text and not any("tell" in str(c) for c in corrections):
            if "sports" in input_text or "something" in input_text:
                issues.append(f"  • '{r['input']}' - 'tell' 可能是 'talk about' 的错误，但未修正")
        
        # 检查过去时错误
        if "yesterday" in input_text and "go" in input_text.split() and "went" not in input_text:
            if not any("went" in str(c) for c in corrections):
                issues.append(f"  • '{r['input']}' - 过去时错误可能未修正")
    
    if issues:
        for issue in issues:
            print(issue)
    else:
        print("  (未发现明显问题)")

print("\n" + "=" * 100)


