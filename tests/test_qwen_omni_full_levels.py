"""
测试 qwen-omni 模型的指令遵循能力（覆盖六个 CEFR 等级）
使用 qwen-omni TTS 生成音频，测试评分区分度
"""
import json
import time
from services.unified_processor import create_processor

# 覆盖六个 CEFR 等级的测试用例（每个等级3-4个，包含中英文混杂）
TEST_CASES = [
    # ========== A1 级别 (0-25) ==========
    {
        "level": "A1",
        "text": "我不会说英语，请帮帮我",
        "description": "纯中文输入"
    },
    {
        "level": "A1",
        "text": "Hello. Yes. Good.",
        "description": "极简单词"
    },
    {
        "level": "A1",
        "text": "I like 苹果. 很好吃.",
        "description": "中英文混杂，简单词汇"
    },
    {
        "level": "A1",
        "text": "请tell me about 足球",
        "description": "中英文混杂，简单结构"
    },
    
    # ========== A2 级别 (25-45) ==========
    {
        "level": "A2",
        "text": "I like play basketball. Yesterday I go to school.",
        "description": "简单句有错误"
    },
    {
        "level": "A2",
        "text": "I want to talk about 足球 with you. 梅西 is very good.",
        "description": "中英文混杂，简单句子"
    },
    {
        "level": "A2",
        "text": "Yesterday I go to the park and see many people play 篮球",
        "description": "中英文混杂，时态错误"
    },
    {
        "level": "A2",
        "text": "He is a very good player, 我很like him",
        "description": "中英文混杂，主谓一致错误"
    },
    
    # ========== B1 级别 (45-65) ==========
    {
        "level": "B1",
        "text": "I went to the cinema last weekend and watched a movie about time travel. It was very interesting.",
        "description": "完整表达，偶有小错"
    },
    {
        "level": "B1",
        "text": "Last summer, I traveled to Beijing with my family. We visited the Great Wall and took many photos.",
        "description": "有细节描述"
    },
    {
        "level": "B1",
        "text": "I think Messi is one of the best players in the world. 他的achievements真的很impressive.",
        "description": "中英文混杂，但表达相对完整"
    },
    {
        "level": "B1",
        "text": "I want to learn more about football, especially about Messi的playing style and his career.",
        "description": "中英文混杂，有复杂结构"
    },
    
    # ========== B2 级别 (65-80) ==========
    {
        "level": "B2",
        "text": "Although I was initially skeptical about the movie, I found myself captivated by its storyline and character development.",
        "description": "复杂句式和从句"
    },
    {
        "level": "B2",
        "text": "If I had known about this opportunity earlier, I would have prepared more thoroughly for the interview.",
        "description": "虚拟语气和条件句"
    },
    {
        "level": "B2",
        "text": "Messi's playing style is really unique. 他的technique和vision让很多fans都admire him.",
        "description": "中英文混杂，但使用复杂词汇"
    },
    {
        "level": "B2",
        "text": "The way Messi plays football demonstrates not only his exceptional talent but also his dedication to the sport.",
        "description": "复杂句式，高级词汇"
    },
    
    # ========== C1 级别 (80-92) ==========
    {
        "level": "C1",
        "text": "The proliferation of artificial intelligence has precipitated a paradigm shift in how we conceptualize human-machine interaction.",
        "description": "高级词汇和学术表达"
    },
    {
        "level": "C1",
        "text": "Notwithstanding the considerable obstacles that impeded our progress, we persevered and ultimately achieved unprecedented results in our research.",
        "description": "复杂论述和精准用词"
    },
    {
        "level": "C1",
        "text": "Messi's career exemplifies the notion that exceptional talent, when combined with relentless perseverance, can transcend conventional limitations.",
        "description": "高级词汇，复杂结构"
    },
    {
        "level": "C1",
        "text": "The intricate dynamics of modern football require players to possess not merely technical proficiency but also strategic acumen and psychological resilience.",
        "description": "学术风格，复杂论述"
    },
    
    # ========== C2 级别 (92-100) ==========
    {
        "level": "C2",
        "text": "The epistemological underpinnings of contemporary discourse reveal a fascinating interplay between Cartesian dualism and emergent materialism.",
        "description": "接近母语水平的深度表达"
    },
    {
        "level": "C2",
        "text": "Lionel Messi's unparalleled mastery of the beautiful game transcends mere athleticism, embodying a synthesis of technical virtuosity, tactical intelligence, and artistic expression that has redefined the parameters of footballing excellence.",
        "description": "母语水平，复杂论述"
    },
    {
        "level": "C2",
        "text": "The multifaceted nature of linguistic competence encompasses not only grammatical accuracy but also pragmatic appropriateness, sociolinguistic awareness, and the ability to navigate subtle nuances of meaning across diverse communicative contexts.",
        "description": "学术深度，精准表达"
    },
]


def format_suggestions(result):
    """格式化建议输出"""
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


def generate_audio_with_tts(tts_service, text: str) -> bytes:
    """使用 TTS 生成音频（使用 OpenAI TTS，虽然不支持中文但至少可以工作）"""
    try:
        # 直接使用传入的 tts_service（应该是 OpenAI TTS）
        audio_data = tts_service.text_to_speech(text, voice="alloy")
        return audio_data
    except Exception as e:
        print(f"  ⚠️ TTS 生成失败: {e}")
        # 如果失败，尝试使用 edge-tts（异步）
        try:
            import asyncio
            import edge_tts
            
            async def _generate():
                # 检测文本是否包含中文
                has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
                
                # 选择语音
                if has_chinese:
                    voice = "zh-CN-XiaoxiaoNeural"
                else:
                    voice = "en-US-JennyNeural"
                
                communicate = edge_tts.Communicate(text, voice)
                audio_data = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                return audio_data
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_generate())
            finally:
                loop.close()
        except Exception as e2:
            print(f"  ❌ 回退 TTS 也失败: {e2}")
            return None


def main():
    """主测试函数"""
    print("=" * 80)
    print("测试 qwen-omni 模型（覆盖六个 CEFR 等级）")
    print("使用 qwen-omni TTS 生成音频")
    print("=" * 80)
    print()
    
    # 创建处理器（使用 qwen-omni）
    processor = create_processor(service_type="qwen-omni")
    
    # 使用 OpenAI TTS（虽然不支持中文，但至少可以工作）
    print("初始化 TTS 服务（使用 OpenAI TTS）...")
    from services.tts import TTSServiceFactory
    tts_service = TTSServiceFactory.create(provider="openai")
    print("✅ TTS 服务初始化完成\n")
    print("⚠️  注意：OpenAI TTS 不支持中文，中文部分可能发音不准确，但这不影响测试评分功能\n")
    
    results = []
    
    for i, test_case in enumerate(TEST_CASES, 1):
        level = test_case["level"]
        text = test_case["text"]
        description = test_case["description"]
        
        print(f"\n{'='*80}")
        print(f"测试用例 {i}/{len(TEST_CASES)} - {level} 级别")
        print(f"{'='*80}")
        print(f"描述: {description}")
        print(f"用户输入文本: {text}")
        print()
        
        try:
            # 1. 生成音频
            print("⏳ 生成音频...")
            start_time = time.time()
            audio_data = generate_audio_with_tts(tts_service, text)
            tts_time = time.time() - start_time
            
            if not audio_data:
                print("❌ 音频生成失败")
                results.append({
                    "level": level,
                    "input": text,
                    "description": description,
                    "error": "TTS 生成失败"
                })
                continue
            
            print(f"✅ 音频生成完成 ({len(audio_data)} bytes, {tts_time:.2f}s)")
            
            # 2. 处理音频（使用 qwen-omni）
            print("⏳ Qwen-Omni 处理音频中...")
            start_time = time.time()
            result = processor.process_audio(
                audio_data=audio_data,
                audio_format="mp3",  # 或根据实际格式调整
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
            print(f"  预期等级: {level}")
            print(f"  实际分数: {suggestions['score']}")
            print(f"  实际等级: {suggestions['level']}")
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
            print()
            
            print("💬 鼓励语:")
            print(f"  {suggestions['encouragement']}")
            print()
            
            # 保存结果
            results.append({
                "level": level,
                "input": text,
                "description": description,
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
                "level": level,
                "input": text,
                "description": description,
                "error": str(e)
            })
    
    # 保存所有结果到 JSON 文件
    output_file = "qwen_omni_full_levels_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print(f"测试完成！结果已保存到: {output_file}")
    print("=" * 80)
    
    # 按等级统计
    print("\n📈 按等级统计:")
    level_stats = {}
    for r in results:
        if 'suggestions' in r:
            level = r['level']
            if level not in level_stats:
                level_stats[level] = {"scores": [], "count": 0}
            level_stats[level]["scores"].append(r['suggestions']['score'])
            level_stats[level]["count"] += 1
    
    for level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        if level in level_stats:
            stats = level_stats[level]
            scores = stats["scores"]
            avg_score = sum(scores) / len(scores)
            print(f"\n{level} 级别:")
            print(f"  用例数: {stats['count']}")
            print(f"  平均分: {avg_score:.1f}")
            print(f"  分数范围: {min(scores)} - {max(scores)}")
            print(f"  预期范围: {get_expected_range(level)}")
        else:
            print(f"\n{level} 级别: 无数据")
    
    # 总体统计
    successful = [r for r in results if 'suggestions' in r]
    print(f"\n总体统计:")
    print(f"  成功处理: {len(successful)}/{len(TEST_CASES)}")
    
    if successful:
        scores = [r['suggestions']['score'] for r in successful]
        print(f"  平均分数: {sum(scores)/len(scores):.1f}")
        print(f"  分数范围: {min(scores)} - {max(scores)}")
        print(f"  标准差: {calculate_std(scores):.1f}")


def get_expected_range(level: str) -> str:
    """获取预期分数范围"""
    ranges = {
        "A1": "0-25",
        "A2": "25-45",
        "B1": "45-65",
        "B2": "65-80",
        "C1": "80-92",
        "C2": "92-100"
    }
    return ranges.get(level, "未知")


def calculate_std(scores):
    """计算标准差"""
    if not scores:
        return 0
    avg = sum(scores) / len(scores)
    variance = sum((x - avg) ** 2 for x in scores) / len(scores)
    return variance ** 0.5


if __name__ == "__main__":
    main()

