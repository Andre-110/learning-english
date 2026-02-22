"""
自动化测试：TextPreprocessor 和语义完整性检查

从维度二、三的测试用例中提取可自动化的部分：
- 废词过滤
- 意图切换检测
- 语义完整性判断
"""
import sys
sys.path.insert(0, '/home/ubuntu/learning_english')

from services.text_preprocessor import TextPreprocessor
from services.unified_processor import ResponseParser

# 创建 TextPreprocessor 实例
preprocessor = TextPreprocessor()


def test_filler_word_filtering():
    """测试废词过滤 - 对应维度二用例7"""
    print("\n" + "=" * 60)
    print("测试1: 废词过滤（维度二 用例7）")
    print("=" * 60)
    
    test_cases = [
        # (输入, 预期核心内容)
        ("那个...我想问一下...呃...就是...现在的油价。", "油价"),
        ("Well... you know... I actually... love jazz.", "love jazz"),
        ("Um, uh, like, I mean, the weather is nice.", "weather is nice"),
        ("呃 嗯 那个 我想吃饭", "我想吃饭"),
    ]
    
    passed = 0
    for text, expected_keyword in test_cases:
        cleaned, fillers = preprocessor.filter_filler_words(text)
        has_keyword = expected_keyword.lower() in cleaned.lower()
        status = "✅ PASS" if has_keyword else "❌ FAIL"
        print(f"\n输入: {text}")
        print(f"过滤后: {cleaned}")
        print(f"被过滤: {fillers}")
        print(f"包含关键词 '{expected_keyword}': {status}")
        if has_keyword:
            passed += 1
    
    print(f"\n结果: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


def test_intent_switch_detection():
    """测试意图切换检测 - 对应维度二用例10"""
    print("\n" + "=" * 60)
    print("测试2: 意图切换检测（维度二 用例10）")
    print("=" * 60)
    
    test_cases = [
        # (输入, 预期最终意图关键词, 是否有切换)
        ("帮我查一下，算了，帮我放首歌吧。", "放首歌", True),
        ("订个外卖，不用了，我自己做饭。", "自己做饭", True),
        ("Never mind, just play some music.", "play some music", True),
        ("帮我查天气", "查天气", False),  # 无切换
    ]
    
    passed = 0
    for text, expected_keyword, should_switch in test_cases:
        has_switch, cancel_word, new_intent = preprocessor.detect_intent_switch(text)
        has_keyword = expected_keyword in new_intent
        detected_switch = cancel_word is not None
        
        correct = has_keyword and (detected_switch == should_switch)
        status = "✅ PASS" if correct else "❌ FAIL"
        
        print(f"\n输入: {text}")
        print(f"检测到切换词: {cancel_word}")
        print(f"最终意图: {new_intent}")
        print(f"包含 '{expected_keyword}': {has_keyword}, 切换检测: {detected_switch} (预期: {should_switch})")
        print(f"结果: {status}")
        if correct:
            passed += 1
    
    print(f"\n结果: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


def test_semantic_completeness():
    """测试语义完整性判断 - 对应维度二用例6、维度三用例1,4"""
    print("\n" + "=" * 60)
    print("测试3: 语义完整性判断（维度二 用例6，维度三 用例1,4）")
    print("=" * 60)
    
    test_cases = [
        # (输入, 预期是否完整)
        # 不完整的句子
        ("I think the most important thing in life is", False),  # 维度三用例1
        ("I'm interested in", False),  # 维度三用例4
        ("我要订一张", False),  # 维度二用例6（部分）
        ("The weather is", False),
        ("I want to", False),
        ("Because", False),
        ("If you", False),
        
        # 完整的句子
        ("I love jazz.", True),
        ("The weather is nice today.", True),
        ("我想吃饭。", True),
        ("My hobby is playing basketball.", True),
        ("I'm happy!", True),
    ]
    
    passed = 0
    for text, expected_complete in test_cases:
        is_complete, confidence = TextPreprocessor.is_semantically_complete(text)
        correct = is_complete == expected_complete
        status = "✅ PASS" if correct else "❌ FAIL"
        
        print(f"\n输入: '{text}'")
        print(f"完整性: {is_complete} (置信度: {confidence:.2f}), 预期: {expected_complete}")
        print(f"结果: {status}")
        if correct:
            passed += 1
    
    print(f"\n结果: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


def test_trailing_sound_normalization():
    """测试拖音处理 - 对应维度二用例8"""
    print("\n" + "=" * 60)
    print("测试4: 拖音处理（维度二 用例8）")
    print("=" * 60)
    
    test_cases = [
        # (输入, 预期输出)
        ("那——个——", "那个"),
        ("umm————", "um"),
        ("hellooooo", "helo"),  # 注意：会把 ll 和 oo 都去重
        ("yeahhhhh", "yeah"),
        ("正常文本", "正常文本"),
    ]
    
    passed = 0
    for text, expected in test_cases:
        normalized = TextPreprocessor.normalize_trailing_sounds(text)
        correct = normalized == expected
        status = "✅ PASS" if correct else "❌ FAIL"
        
        print(f"\n输入: '{text}'")
        print(f"标准化: '{normalized}', 预期: '{expected}'")
        print(f"结果: {status}")
        if correct:
            passed += 1
    
    print(f"\n结果: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


def test_response_parser_sentence_complete():
    """测试 ResponseParser.is_sentence_complete - 集成测试"""
    print("\n" + "=" * 60)
    print("测试5: ResponseParser.is_sentence_complete 集成测试")
    print("=" * 60)
    
    test_cases = [
        # 英文不完整
        ("Well you know I actually", False),
        ("I think", False),
        ("The most important thing is", False),
        
        # 英文完整
        ("I love playing basketball.", True),
        ("My name is John.", True),
        ("That sounds great!", True),
        
        # 中文（简化处理）
        ("我想", False),  # 可能判断为完整，取决于实现
        ("我喜欢打篮球。", True),
    ]
    
    passed = 0
    for text, expected_complete in test_cases:
        is_complete = ResponseParser.is_sentence_complete(text)
        correct = is_complete == expected_complete
        status = "✅ PASS" if correct else "❌ FAIL"
        
        print(f"\n输入: '{text}'")
        print(f"完整性: {is_complete}, 预期: {expected_complete}")
        print(f"结果: {status}")
        if correct:
            passed += 1
    
    print(f"\n结果: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


def main():
    print("\n" + "=" * 60)
    print("🧪 自动化测试：TextPreprocessor & 语义分析")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("废词过滤", test_filler_word_filtering()))
    results.append(("意图切换检测", test_intent_switch_detection()))
    results.append(("语义完整性判断", test_semantic_completeness()))
    results.append(("拖音处理", test_trailing_sound_normalization()))
    results.append(("ResponseParser 集成", test_response_parser_sentence_complete()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试汇总")
    print("=" * 60)
    
    total_passed = 0
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name}: {status}")
        if passed:
            total_passed += 1
    
    print(f"\n总计: {total_passed}/{len(results)} 测试组通过")
    
    if total_passed == len(results):
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print("\n⚠️ 部分测试失败，请检查实现")
        return 1


if __name__ == "__main__":
    exit(main())

