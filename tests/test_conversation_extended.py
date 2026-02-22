"""
扩展的多轮对话测试 - 测试处理时间随轮数增加的变化趋势
生成大量轮次的对话，观察上下文压缩对处理时间的影响
"""
import json
import time
from services.unified_processor import create_processor
from services.tts import TTSServiceFactory

# 扩展的对话场景 - 每个场景包含更多轮次
EXTENDED_SCENARIOS = [
    {
        "name": "场景1：足球兴趣深入探索（20轮）",
        "user_profile": None,
        "turns": [
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
    },
    {
        "name": "场景2：电影话题深入（20轮）",
        "user_profile": None,
        "turns": [
            "Hi! I watched a movie yesterday.",
            "It was about time travel. Very interesting.",
            "Have you seen Interstellar?",
            "I prefer science fiction movies.",
            "What other sci-fi movies do you recommend?",
            "What about Blade Runner?",
            "Is it similar to Interstellar?",
            "What makes a good sci-fi movie?",
            "Do you like space movies?",
            "What about alien movies?",
            "Have you seen Arrival?",
            "What did you think of it?",
            "What about The Matrix?",
            "Is it still relevant today?",
            "What about newer sci-fi movies?",
            "Any recommendations from recent years?",
            "What about Dune?",
            "Is it worth watching?",
            "What makes sci-fi movies interesting?",
            "Can you recommend more?"
        ]
    },
    {
        "name": "场景3：英语学习深入（20轮）",
        "user_profile": None,
        "turns": [
            "I want to improve my English.",
            "I need it for my job.",
            "I work in a technology company.",
            "We have many international clients.",
            "So I need to communicate better in English.",
            "What should I focus on first?",
            "Should I practice speaking more?",
            "How can I improve my vocabulary?",
            "What about grammar?",
            "Is grammar important?",
            "How can I practice listening?",
            "What about reading?",
            "Should I read English books?",
            "What kind of books?",
            "How about watching English movies?",
            "Should I use subtitles?",
            "How can I practice writing?",
            "Should I keep a journal?",
            "What about pronunciation?",
            "How can I improve it?"
        ]
    }
]


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
    print("扩展的多轮对话测试 - 处理时间趋势分析")
    print("测试指标：处理时间随轮数增加的变化")
    print("=" * 100)
    print()
    
    # 创建处理器
    processor = create_processor(service_type="qwen-omni")
    
    # 创建 TTS 服务
    print("初始化 TTS 服务...")
    tts_service = TTSServiceFactory.create(provider="openai")
    print("✅ TTS 服务初始化完成\n")
    
    all_results = []
    
    for scenario_idx, scenario in enumerate(EXTENDED_SCENARIOS, 1):
        print(f"\n{'='*100}")
        print(f"场景 {scenario_idx}/{len(EXTENDED_SCENARIOS)}: {scenario['name']}")
        print(f"{'='*100}\n")
        
        user_profile = None
        conversation_history = []
        turn_times = []
        turn_results = []
        
        for turn_idx, user_text in enumerate(scenario['turns'], 1):
            print(f"--- Turn {turn_idx}/{len(scenario['turns'])} ---")
            print(f"用户: {user_text}")
            
            try:
                # 1. 生成音频
                start_time = time.time()
                audio_data = generate_audio(tts_service, user_text)
                tts_time = time.time() - start_time
                
                if not audio_data:
                    print("❌ 音频生成失败")
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
                
                # 3. 更新用户画像（模拟）
                if user_profile is None:
                    user_profile = {
                        "overall_score": result.evaluation.get("overall_score", 50),
                        "cefr_level": result.evaluation.get("cefr_level", "A2"),
                        "strengths": [],
                        "weaknesses": [],
                        "interests": []
                    }
                
                # 合并兴趣
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
                print(f"处理时间: {process_time:.2f}s")
                print(f"对话历史长度: {len(conversation_history)}条消息")
                print()
                
                # 保存本轮结果
                turn_results.append({
                    "turn": turn_idx,
                    "user_input": user_text,
                    "transcription": result.transcription,
                    "ai_response": result.full_response,
                    "score": result.evaluation.get("overall_score", 0),
                    "level": result.evaluation.get("cefr_level", ""),
                    "interests": new_interests,
                    "process_time": process_time,
                    "tts_time": tts_time,
                    "conversation_history_length": len(conversation_history)
                })
                
            except Exception as e:
                print(f"❌ 处理失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 场景总结
        print(f"\n{'='*100}")
        print(f"场景总结: {scenario['name']}")
        print(f"{'='*100}")
        
        if turn_times:
            avg_time = sum(turn_times) / len(turn_times)
            max_time = max(turn_times)
            min_time = min(turn_times)
            
            # 分段分析
            if len(turn_times) >= 4:
                first_quarter = turn_times[:len(turn_times)//4]
                second_quarter = turn_times[len(turn_times)//4:len(turn_times)//2]
                third_quarter = turn_times[len(turn_times)//2:3*len(turn_times)//4]
                fourth_quarter = turn_times[3*len(turn_times)//4:]
                
                print(f"\n处理时延分段分析:")
                print(f"  第1段（前{len(first_quarter)}轮）平均: {sum(first_quarter)/len(first_quarter):.2f}s")
                print(f"  第2段（第{len(first_quarter)+1}-{len(first_quarter)+len(second_quarter)}轮）平均: {sum(second_quarter)/len(second_quarter):.2f}s")
                print(f"  第3段（第{len(first_quarter)+len(second_quarter)+1}-{len(first_quarter)+len(second_quarter)+len(third_quarter)}轮）平均: {sum(third_quarter)/len(third_quarter):.2f}s")
                print(f"  第4段（后{len(fourth_quarter)}轮）平均: {sum(fourth_quarter)/len(fourth_quarter):.2f}s")
                
                # 计算增长趋势
                first_avg = sum(first_quarter) / len(first_quarter)
                last_avg = sum(fourth_quarter) / len(fourth_quarter)
                growth = ((last_avg / first_avg - 1) * 100) if first_avg > 0 else 0
                print(f"  总体增长: {growth:+.1f}%")
            
            print(f"\n处理时延统计:")
            print(f"  平均: {avg_time:.2f}s")
            print(f"  范围: {min_time:.2f}s - {max_time:.2f}s")
            print(f"  各轮时间: {[f'{t:.2f}s' for t in turn_times]}")
        
        # 保存场景结果
        all_results.append({
            "scenario": scenario['name'],
            "turns": turn_results,
            "timing_analysis": {
                "avg_time": avg_time if turn_times else 0,
                "max_time": max_time if turn_times else 0,
                "min_time": min_time if turn_times else 0,
                "all_times": turn_times
            }
        })
    
    # 保存所有结果
    output_file = "conversation_extended_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n\n{'='*100}")
    print("总体统计")
    print(f"{'='*100}")
    
    # 总体统计
    total_turns = sum(len(r['turns']) for r in all_results)
    all_times = []
    for r in all_results:
        all_times.extend(r['timing_analysis']['all_times'])
    
    print(f"\n总体指标:")
    print(f"  总对话轮数: {total_turns}")
    print(f"  平均处理时延: {sum(all_times)/len(all_times):.2f}s" if all_times else "  N/A")
    
    # 按轮次分组统计
    turn_groups = {}
    for r in all_results:
        for turn in r['turns']:
            turn_num = turn['turn']
            if turn_num not in turn_groups:
                turn_groups[turn_num] = []
            turn_groups[turn_num].append(turn['process_time'])
    
    print(f"\n各轮次平均处理时间:")
    for turn_num in sorted(turn_groups.keys()):
        times = turn_groups[turn_num]
        avg_time = sum(times) / len(times)
        print(f"  Turn {turn_num}: {avg_time:.2f}s (样本数: {len(times)})")
    
    print(f"\n结果已保存到: {output_file}")


if __name__ == "__main__":
    main()


