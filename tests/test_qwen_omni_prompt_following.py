"""
测试 qwen-omni 模型的 prompt 遵循能力
重点测试：中英文识别、建议质量、中英文转录准确性
使用之前的20个中英文混杂用例
"""
import json
import time
from services.unified_processor import create_processor
from services.tts import TTSServiceFactory

# 20个中英文混杂的测试用例（与之前相同）
TEST_CASES = [
    "I want to talk some thing about 足球player with you",
    "请继续详细地介绍一下Messi的故事",
    "I play for 土豆and 番茄because they are delicious",
    "这个football player真的很amazing，我想知道more about him",
    "Yesterday I go to the park and see many people play 篮球",
    "请tell me more about Messi的achievements",
    "I think this story tell me how to face 困难",
    "我想了解more about football，特别是about Messi",
    "He is a very good player, 我很like him",
    "请continue介绍Messi的childhood，我想知道more details",
    "I want to tell some 运动with you",
    "这个player真的很great，他的story很inspiring",
    "Yesterday I see a movie about football, 它was very interesting",
    "请explain more about Messi的playing style",
    "I think football is a very good sport, 我喜欢to watch it",
    "我想知道more about Messi的family life",
    "He play football very well, 我很admire him",
    "请继续talk about Messi的career，特别是his early years",
    "I want to learn English better so I can talk about 运动",
    "这个player的achievements真的很impressive，我想知道how he did it"
]


def generate_audio_with_tts(tts_service, text: str) -> bytes:
    """使用 TTS 生成音频（使用 OpenAI TTS）"""
    try:
        audio_data = tts_service.text_to_speech(text, voice="alloy")
        return audio_data
    except Exception as e:
        print(f"  ⚠️ TTS 生成失败: {e}")
        return None


def analyze_transcription_quality(original_text: str, transcription: str) -> dict:
    """分析转录质量"""
    analysis = {
        "original": original_text,
        "transcription": transcription,
        "chinese_preserved": True,
        "english_preserved": True,
        "chinese_errors": [],
        "english_errors": [],
        "mixed_preserved": True
    }
    
    # 检查中文部分是否保留
    import re
    chinese_in_original = re.findall(r'[\u4e00-\u9fff]+', original_text)
    chinese_in_transcription = re.findall(r'[\u4e00-\u9fff]+', transcription)
    
    # 检查每个中文词是否在转录中
    for chinese_word in chinese_in_original:
        if chinese_word not in transcription:
            analysis["chinese_preserved"] = False
            analysis["chinese_errors"].append(f"缺失: {chinese_word}")
    
    # 检查是否有额外的中文（可能是误听）
    for chinese_word in chinese_in_transcription:
        if chinese_word not in original_text:
            analysis["chinese_errors"].append(f"多余: {chinese_word}")
    
    # 检查英文关键词是否保留
    english_words = re.findall(r'[a-zA-Z]+', original_text)
    for word in english_words:
        if len(word) > 3:  # 只检查较长的词
            if word.lower() not in transcription.lower():
                analysis["english_errors"].append(f"缺失或错误: {word}")
    
    # 检查中英文混杂是否保留
    has_chinese_original = bool(chinese_in_original)
    has_chinese_transcription = bool(chinese_in_transcription)
    has_english_original = bool(re.search(r'[a-zA-Z]', original_text))
    has_english_transcription = bool(re.search(r'[a-zA-Z]', transcription))
    
    if has_chinese_original and not has_chinese_transcription:
        analysis["mixed_preserved"] = False
    if has_english_original and not has_english_transcription:
        analysis["mixed_preserved"] = False
    
    return analysis


def analyze_suggestions_quality(suggestions: dict, original_text: str) -> dict:
    """分析建议质量"""
    analysis = {
        "has_corrections": len(suggestions.get("corrections", [])) > 0,
        "corrections_count": len(suggestions.get("corrections", [])),
        "redundant_corrections": [],
        "chinese_handled": False,
        "score_reasonable": True,
        "encouragement_present": bool(suggestions.get("encouragement", ""))
    }
    
    # 检查冗余修正（original == corrected）
    corrections = suggestions.get("corrections", [])
    for corr in corrections:
        if isinstance(corr, dict):
            orig = corr.get("original", "").lower().strip()
            corr_text = corr.get("corrected", "").lower().strip()
            if orig == corr_text:
                analysis["redundant_corrections"].append(corr)
    
    # 检查是否处理了中文部分
    import re
    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', original_text))
    if has_chinese:
        # 检查是否有针对中文的修正建议
        for corr in corrections:
            if isinstance(corr, dict):
                orig = corr.get("original", "")
                if re.search(r'[\u4e00-\u9fff]', orig):
                    analysis["chinese_handled"] = True
                    break
    
    # 检查分数是否合理（中英文混杂应该25-40分）
    score = suggestions.get("score", 0)
    if has_chinese:
        if score > 40:
            analysis["score_reasonable"] = False
    
    return analysis


def main():
    """主测试函数"""
    print("=" * 80)
    print("测试 qwen-omni 模型的 prompt 遵循能力")
    print("重点：中英文识别、建议质量、中英文转录准确性")
    print("=" * 80)
    print()
    
    # 创建处理器（使用 qwen-omni）
    processor = create_processor(service_type="qwen-omni")
    
    # 使用 OpenAI TTS（edge-tts 在当前环境不可用）
    print("初始化 TTS 服务（使用 OpenAI TTS）...")
    print("⚠️  注意：OpenAI TTS 不支持中文，中文部分可能发音不准确")
    print("⚠️  但 prompt 已优化，模型应能识别拼音化的中文并修正\n")
    tts_service = TTSServiceFactory.create(provider="openai")
    print("✅ TTS 服务初始化完成\n")
    
    results = []
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n{'='*80}")
        print(f"测试用例 {i}/20")
        print(f"{'='*80}")
        print(f"用户输入: {test_case}")
        print()
        
        try:
            # 1. 生成音频
            print("⏳ 生成音频...")
            start_time = time.time()
            audio_data = generate_audio_with_tts(tts_service, test_case)
            tts_time = time.time() - start_time
            
            if not audio_data:
                print("❌ 音频生成失败")
                results.append({
                    "input": test_case,
                    "error": "TTS 生成失败"
                })
                continue
            
            print(f"✅ 音频生成完成 ({len(audio_data)} bytes, {tts_time:.2f}s)")
            
            # 2. 处理音频
            print("⏳ Qwen-Omni 处理音频中...")
            start_time = time.time()
            result = processor.process_audio(
                audio_data=audio_data,
                audio_format="mp3",
                conversation_history=None,
                user_profile=None
            )
            omni_time = time.time() - start_time
            print(f"✅ 处理完成 ({omni_time:.2f}s)")
            print()
            
            # 3. 分析转录质量
            transcription_analysis = analyze_transcription_quality(test_case, result.transcription)
            
            # 4. 分析建议质量
            suggestions = {
                "score": result.evaluation.get("overall_score", 0),
                "level": result.evaluation.get("cefr_level", "A2"),
                "strengths": result.evaluation.get("strengths", []),
                "weaknesses": result.evaluation.get("weaknesses", []),
                "corrections": result.evaluation.get("corrections", []),
                "good_expressions": result.evaluation.get("good_expressions", []),
                "encouragement": result.evaluation.get("encouragement", "")
            }
            suggestions_analysis = analyze_suggestions_quality(suggestions, test_case)
            
            # 5. 展示结果
            print("📝 转录结果:")
            print(f"  原文: {test_case}")
            print(f"  转录: {result.transcription}")
            
            if not transcription_analysis["chinese_preserved"]:
                print(f"  ⚠️  中文部分未保留: {transcription_analysis['chinese_errors']}")
            if transcription_analysis["chinese_errors"]:
                print(f"  ⚠️  中文转录错误: {transcription_analysis['chinese_errors']}")
            if transcription_analysis["english_errors"]:
                print(f"  ⚠️  英文转录错误: {transcription_analysis['english_errors']}")
            
            print()
            print("📊 评估结果:")
            print(f"  分数: {suggestions['score']} ({suggestions['level']})")
            
            print()
            print("✏️  修正建议:")
            if suggestions['corrections']:
                for j, correction in enumerate(suggestions['corrections'], 1):
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
            
            if suggestions_analysis["redundant_corrections"]:
                print(f"  ⚠️  冗余修正: {len(suggestions_analysis['redundant_corrections'])}个")
            
            if not suggestions_analysis["chinese_handled"] and any('\u4e00' <= c <= '\u9fff' for c in test_case):
                print(f"  ⚠️  未处理中文部分")
            
            print()
            print("💬 鼓励语:")
            print(f"  {suggestions['encouragement']}")
            print()
            
            # 保存结果
            results.append({
                "input": test_case,
                "transcription": result.transcription,
                "transcription_analysis": transcription_analysis,
                "suggestions": suggestions,
                "suggestions_analysis": suggestions_analysis,
                "response": result.full_response,
                "tts_time": tts_time,
                "omni_time": omni_time
            })
            
        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "input": test_case,
                "error": str(e)
            })
    
    # 保存结果
    output_file = "qwen_omni_prompt_following_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print(f"测试完成！结果已保存到: {output_file}")
    print("=" * 80)
    
    # 统计摘要
    successful = [r for r in results if 'transcription' in r]
    print(f"\n📈 统计摘要:")
    print(f"  成功处理: {len(successful)}/20")
    
    if successful:
        # 转录质量统计
        chinese_preserved_count = sum(1 for r in successful 
                                     if r.get('transcription_analysis', {}).get('chinese_preserved', False))
        mixed_preserved_count = sum(1 for r in successful 
                                   if r.get('transcription_analysis', {}).get('mixed_preserved', False))
        
        print(f"\n转录质量:")
        print(f"  中文保留率: {chinese_preserved_count}/{len(successful)} ({chinese_preserved_count/len(successful)*100:.1f}%)")
        print(f"  中英文混杂保留率: {mixed_preserved_count}/{len(successful)} ({mixed_preserved_count/len(successful)*100:.1f}%)")
        
        # 建议质量统计
        total_corrections = sum(len(r.get('suggestions', {}).get('corrections', [])) for r in successful)
        redundant_count = sum(len(r.get('suggestions_analysis', {}).get('redundant_corrections', [])) 
                             for r in successful)
        chinese_handled_count = sum(1 for r in successful 
                                   if r.get('suggestions_analysis', {}).get('chinese_handled', False))
        
        print(f"\n建议质量:")
        print(f"  总修正数: {total_corrections}")
        print(f"  冗余修正: {redundant_count}")
        print(f"  中文处理率: {chinese_handled_count}/{len(successful)} ({chinese_handled_count/len(successful)*100:.1f}%)")
        
        # 分数统计
        scores = [r.get('suggestions', {}).get('score', 0) for r in successful]
        avg_score = sum(scores) / len(scores)
        print(f"\n评分:")
        print(f"  平均分数: {avg_score:.1f}")
        print(f"  分数范围: {min(scores)} - {max(scores)}")


if __name__ == "__main__":
    main()

