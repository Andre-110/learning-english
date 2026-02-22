"""
测试 qwen-omni 模型的指令遵循能力（使用音频输入）
生成20个中英文混杂的例子，展示模型输出的建议
"""
import json
import time
from services.unified_processor import create_processor
from services.tts import TTSServiceFactory

# 20个中英文混杂的测试用例（确保每个都包含中文和英文）
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


def format_suggestions(result):
    """格式化建议输出，展示给前端的内容"""
    eval_data = result.evaluation
    
    suggestions = {
        "score": eval_data.get("overall_score", 0),
        "level": eval_data.get("cefr_level", "A2"),
        "strengths": eval_data.get("strengths", []),
        "weaknesses": eval_data.get("weaknesses", []),
        "corrections": eval_data.get("corrections", []),
        "good_expressions": eval_data.get("good_expressions", []),
        "encouragement": eval_data.get("encouragement", "")
    }
    
    return suggestions


def generate_audio(tts_service, text: str) -> bytes:
    """使用 TTS 生成音频"""
    try:
        # 使用英文语音生成（即使内容有中文）
        audio_data = tts_service.text_to_speech(text, voice="alloy")
        return audio_data
    except Exception as e:
        print(f"  ⚠️ TTS 生成失败: {e}")
        return None


def main():
    """主测试函数"""
    print("=" * 80)
    print("测试 qwen-omni 模型的指令遵循能力（使用音频输入）")
    print("=" * 80)
    print()
    
    # 创建处理器（使用 qwen-omni）
    processor = create_processor(service_type="qwen-omni")
    
    # 创建 TTS 服务
    print("初始化 TTS 服务...")
    tts_service = TTSServiceFactory.create(provider="openai")
    print("✅ TTS 服务初始化完成\n")
    
    results = []
    
    # 可以设置只测试前N个用例（用于快速测试）
    # TEST_CASES = TEST_CASES[:5]  # 取消注释以只测试前5个
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n{'='*80}")
        print(f"测试用例 {i}/20")
        print(f"{'='*80}")
        print(f"用户输入文本: {test_case}")
        print()
        
        try:
            # 1. 生成音频
            print("⏳ 生成音频...")
            start_time = time.time()
            audio_data = generate_audio(tts_service, test_case)
            tts_time = time.time() - start_time
            
            if not audio_data:
                print("❌ 音频生成失败")
                results.append({
                    "input": test_case,
                    "error": "TTS 生成失败"
                })
                continue
            
            print(f"✅ 音频生成完成 ({len(audio_data)} bytes, {tts_time:.2f}s)")
            
            # 2. 处理音频（使用 qwen-omni）
            print("⏳ Qwen-Omni 处理音频中...")
            start_time = time.time()
            result = processor.process_audio(
                audio_data=audio_data,
                audio_format="mp3",  # OpenAI TTS 输出 mp3
                conversation_history=None,
                user_profile=None
            )
            omni_time = time.time() - start_time
            print(f"✅ 处理完成 ({omni_time:.2f}s)")
            print()
            
            # 提取建议
            suggestions = format_suggestions(result)
            
            # 展示结果
            print("📊 评估结果:")
            print(f"  分数: {suggestions['score']}")
            print(f"  等级: {suggestions['level']}")
            print()
            
            print("✅ 强项:")
            if suggestions['strengths']:
                for strength in suggestions['strengths']:
                    print(f"  - {strength}")
            else:
                print("  (无)")
            print()
            
            print("⚠️  弱项:")
            if suggestions['weaknesses']:
                for weakness in suggestions['weaknesses']:
                    print(f"  - {weakness}")
            else:
                print("  (无)")
            print()
            
            print("✏️  修正建议:")
            if suggestions['corrections']:
                for correction in suggestions['corrections']:
                    if isinstance(correction, dict):
                        original = correction.get('original', '')
                        corrected = correction.get('corrected', '')
                        explanation = correction.get('explanation', '')
                        print(f"  • {original} → {corrected}")
                        if explanation:
                            print(f"    说明: {explanation}")
                    else:
                        print(f"  • {correction}")
            else:
                print("  (无修正)")
            print()
            
            print("🌟 好的表达:")
            if suggestions['good_expressions']:
                for expr in suggestions['good_expressions']:
                    print(f"  - {expr}")
            else:
                print("  (无)")
            print()
            
            print("💬 鼓励语:")
            print(f"  {suggestions['encouragement']}")
            print()
            
            # 保存结果
            results.append({
                "input": test_case,
                "suggestions": suggestions,
                "transcription": result.transcription,
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
    
    # 保存所有结果到 JSON 文件
    output_file = "qwen_omni_test_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print(f"测试完成！结果已保存到: {output_file}")
    print("=" * 80)
    
    # 统计摘要
    print("\n📈 统计摘要:")
    successful = [r for r in results if 'suggestions' in r]
    print(f"  成功处理: {len(successful)}/20")
    
    if successful:
        avg_score = sum(r['suggestions']['score'] for r in successful) / len(successful)
        print(f"  平均分数: {avg_score:.1f}")
        
        total_corrections = sum(len(r['suggestions']['corrections']) for r in successful)
        print(f"  总修正数: {total_corrections}")
        
        cases_with_corrections = sum(1 for r in successful if r['suggestions']['corrections'])
        print(f"  有修正的用例: {cases_with_corrections}/{len(successful)}")
        
        cases_without_corrections = sum(1 for r in successful if not r['suggestions']['corrections'])
        print(f"  无修正的用例: {cases_without_corrections}/{len(successful)}")


if __name__ == "__main__":
    main()

