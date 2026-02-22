"""
100轮对话测试 - 深度测试处理时间随轮数增加的变化趋势
"""
import json
import time
from services.unified_processor import create_processor
from services.tts import TTSServiceFactory

# 生成100轮对话的模板
def generate_100_turn_conversation():
    """生成100轮关于足球的对话"""
    base_topics = [
        "Hello! I want to talk about football.",
        "I really like Messi. He is amazing.",
        "Can you tell me more about his early career?",
        "What about his achievements in Barcelona?",
        "I also want to know about his family life.",
        "How did he start playing football?",
        "What was his first club?",
        "When did he join Barcelona?",
        "How many goals did he score for Barcelona?",
        "What about his international career?",
        "Did he win the World Cup?",
        "What year did he win it?",
        "Who were his teammates?",
        "What about his playing style?",
        "Is he still playing professionally?",
        "Where does he play now?",
        "How old is he now?",
        "What are his hobbies?",
        "Does he have any charity work?",
        "Can you tell me more about his legacy?"
    ]
    
    # 扩展话题到100轮
    extended_topics = []
    for i in range(100):
        base_idx = i % len(base_topics)
        topic = base_topics[base_idx]
        
        # 添加变化，避免完全重复
        if i > len(base_topics):
            variations = [
                f"Tell me more about {topic.lower()}",
                f"I'm curious about {topic.lower()}",
                f"Can you explain {topic.lower()}?",
                f"What do you think about {topic.lower()}?",
                f"I want to know more about {topic.lower()}",
            ]
            variation_idx = (i // len(base_topics)) % len(variations)
            topic = variations[variation_idx] if variation_idx < len(variations) else topic
        
        extended_topics.append(topic)
    
    return extended_topics


def generate_audio(tts_service, text: str) -> bytes:
    """生成音频"""
    try:
        audio_data = tts_service.text_to_speech(text, voice="alloy")
        return audio_data
    except Exception as e:
        print(f"  ⚠️ TTS 失败: {e}")
        return None


def main():
    """主测试函数"""
    print("=" * 100)
    print("100轮对话测试 - 处理时间趋势深度分析")
    print("=" * 100)
    print()
    
    # 创建处理器
    processor = create_processor(service_type="qwen-omni")
    
    # 创建 TTS 服务
    print("初始化 TTS 服务...")
    tts_service = TTSServiceFactory.create(provider="openai")
    print("✅ TTS 服务初始化完成\n")
    
    # 生成100轮对话
    conversation_turns = generate_100_turn_conversation()
    
    print(f"开始100轮对话测试...")
    print(f"预计时间: 约{len(conversation_turns) * 5 / 60:.1f}分钟\n")
    
    user_profile = None
    conversation_history = []
    turn_results = []
    turn_times = []
    
    start_time = time.time()
    
    for turn_idx, user_text in enumerate(conversation_turns, 1):
        print(f"[{turn_idx:3d}/100] {user_text[:50]}...", end=" ", flush=True)
        
        try:
            # 1. 生成音频
            tts_start = time.time()
            audio_data = generate_audio(tts_service, user_text)
            tts_time = time.time() - tts_start
            
            if not audio_data:
                print("❌ TTS失败")
                continue
            
            # 2. 处理音频（记录处理时间）
            process_start_time = time.time()
            result = processor.process_audio(
                audio_data=audio_data,
                audio_format="mp3",
                conversation_history=conversation_history,
                user_profile=user_profile
            )
            process_time = time.time() - process_start_time
            turn_times.append(process_time)
            
            # 3. 更新用户画像
            if user_profile is None:
                user_profile = {
                    "overall_score": result.evaluation.get("overall_score", 50),
                    "cefr_level": result.evaluation.get("cefr_level", "A2"),
                    "strengths": [],
                    "weaknesses": [],
                    "interests": []
                }
            
            new_interests = result.interests
            if user_profile:
                user_profile["interests"] = list(dict.fromkeys(
                    user_profile.get("interests", []) + new_interests
                ))[-10:]
            
            # 4. 更新对话历史
            conversation_history.append({
                "role": "user",
                "content": result.transcription or user_text
            })
            conversation_history.append({
                "role": "assistant",
                "content": result.full_response
            })
            
            # 5. 显示结果
            print(f"✅ {process_time:.2f}s (历史: {len(conversation_history)}条)")
            
            # 保存本轮结果
            turn_results.append({
                "turn": turn_idx,
                "user_input": user_text,
                "transcription": result.transcription,
                "ai_response": result.full_response[:100] + "..." if len(result.full_response) > 100 else result.full_response,
                "score": result.evaluation.get("overall_score", 0),
                "level": result.evaluation.get("cefr_level", ""),
                "process_time": process_time,
                "tts_time": tts_time,
                "conversation_history_length": len(conversation_history)
            })
            
            # 每10轮显示一次进度统计
            if turn_idx % 10 == 0:
                recent_times = turn_times[-10:]
                avg_recent = sum(recent_times) / len(recent_times)
                elapsed = time.time() - start_time
                remaining = (elapsed / turn_idx) * (100 - turn_idx)
                print(f"\n  📊 进度: {turn_idx}/100 ({turn_idx}%)")
                print(f"  ⏱️  最近10轮平均: {avg_recent:.2f}s")
                print(f"  ⏱️  总耗时: {elapsed/60:.1f}分钟, 预计剩余: {remaining/60:.1f}分钟\n")
            
        except Exception as e:
            print(f"❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    total_time = time.time() - start_time
    
    # 详细分析
    print(f"\n\n{'='*100}")
    print("100轮对话测试完成 - 详细分析")
    print(f"{'='*100}\n")
    
    if turn_times:
        # 分段分析（每10轮一段）
        segments = []
        segment_size = 10
        for i in range(0, len(turn_times), segment_size):
            segment = turn_times[i:i+segment_size]
            segments.append({
                "range": f"Turn {i+1}-{min(i+segment_size, len(turn_times))}",
                "avg_time": sum(segment) / len(segment),
                "min_time": min(segment),
                "max_time": max(segment)
            })
        
        print("分段处理时间分析（每10轮一段）:")
        print(f"{'段':<20} {'平均时间':<12} {'最小':<10} {'最大':<10} {'增长':<10}")
        print("-" * 70)
        
        first_segment_avg = segments[0]["avg_time"]
        for seg in segments:
            growth = ((seg["avg_time"] / first_segment_avg - 1) * 100) if first_segment_avg > 0 else 0
            print(f"{seg['range']:<20} {seg['avg_time']:>8.2f}s   {seg['min_time']:>6.2f}s   {seg['max_time']:>6.2f}s   {growth:>+6.1f}%")
        
        # 总体统计
        print(f"\n总体统计:")
        print(f"  总轮数: {len(turn_times)}")
        print(f"  总耗时: {total_time/60:.2f}分钟 ({total_time:.2f}秒)")
        print(f"  平均处理时间: {sum(turn_times)/len(turn_times):.2f}s")
        print(f"  最快: {min(turn_times):.2f}s (Turn {turn_times.index(min(turn_times))+1})")
        print(f"  最慢: {max(turn_times):.2f}s (Turn {turn_times.index(max(turn_times))+1})")
        
        # 增长趋势分析
        first_10_avg = sum(turn_times[:10]) / 10
        last_10_avg = sum(turn_times[-10:]) / 10
        total_growth = ((last_10_avg / first_10_avg - 1) * 100) if first_10_avg > 0 else 0
        
        print(f"\n增长趋势:")
        print(f"  前10轮平均: {first_10_avg:.2f}s")
        print(f"  后10轮平均: {last_10_avg:.2f}s")
        print(f"  总体增长: {total_growth:+.1f}%")
        
        # 线性趋势分析
        from scipy import stats
        turn_numbers = list(range(1, len(turn_times) + 1))
        slope, intercept, r_value, p_value, std_err = stats.linregress(turn_numbers, turn_times)
        
        print(f"\n线性回归分析:")
        print(f"  斜率: {slope:.4f}秒/轮 (每增加1轮，时间增加{slope:.4f}秒)")
        print(f"  相关系数 (R²): {r_value**2:.4f}")
        print(f"  P值: {p_value:.6f}")
        if p_value < 0.05:
            print(f"  ✅ 统计显著 (p < 0.05) - 处理时间确实随轮数增加而增加")
        else:
            print(f"  ⚠️  统计不显著 (p >= 0.05)")
        
        # 预测100轮后的时间
        predicted_time_100 = intercept + slope * 100
        print(f"\n预测:")
        print(f"  预测Turn 100的处理时间: {predicted_time_100:.2f}s")
    
    # 保存结果
    output_file = "conversation_100_turns_results_no_vpn.json"
    result_data = {
        "total_turns": len(turn_results),
        "total_time_seconds": total_time,
        "turns": turn_results,
        "timing_analysis": {
            "all_times": turn_times,
            "segments": segments if turn_times else [],
            "statistics": {
                "avg_time": sum(turn_times)/len(turn_times) if turn_times else 0,
                "min_time": min(turn_times) if turn_times else 0,
                "max_time": max(turn_times) if turn_times else 0,
                "first_10_avg": sum(turn_times[:10])/10 if len(turn_times) >= 10 else 0,
                "last_10_avg": sum(turn_times[-10:])/10 if len(turn_times) >= 10 else 0,
                "total_growth_percent": total_growth if turn_times else 0
            }
        }
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {output_file}")
    print("=" * 100)


if __name__ == "__main__":
    main()


