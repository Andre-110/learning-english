"""
测试 qwen-omni 多轮对话质量
重点：对话流畅度、兴趣捕捉、上下文压缩时延
使用纯英文避免TTS问题
"""
import json
import time
from services.unified_processor import create_processor
from services.tts import TTSServiceFactory

# 生成多轮对话场景（每个场景包含3-5轮对话）
CONVERSATION_SCENARIOS = [
    {
        "name": "场景1：足球兴趣探索",
        "user_profile": None,  # 新用户
        "turns": [
            "Hello! I want to talk about football.",
            "I really like Messi. He is amazing.",
            "Can you tell me more about his early career?",
            "What about his achievements in Barcelona?",
            "I also want to know about his family life."
        ],
        "expected_interests": ["football", "Messi", "sports"],
        "expected_topics": ["Messi", "football", "career", "achievements", "family"]
    },
    {
        "name": "场景2：电影话题转换",
        "user_profile": None,
        "turns": [
            "Hi! I watched a movie yesterday.",
            "It was about time travel. Very interesting.",
            "Have you seen Interstellar?",
            "I prefer science fiction movies.",
            "What other sci-fi movies do you recommend?"
        ],
        "expected_interests": ["movies", "science fiction", "time travel"],
        "expected_topics": ["movies", "time travel", "Interstellar", "science fiction"]
    },
    {
        "name": "场景3：学习英语动机",
        "user_profile": None,
        "turns": [
            "I want to improve my English.",
            "I need it for my job.",
            "I work in a technology company.",
            "We have many international clients.",
            "So I need to communicate better in English."
        ],
        "expected_interests": ["English learning", "career", "technology"],
        "expected_topics": ["English", "job", "technology", "communication"]
    },
    {
        "name": "场景4：兴趣爱好深入",
        "user_profile": None,
        "turns": [
            "I love reading books.",
            "Especially mystery novels.",
            "Agatha Christie is my favorite author.",
            "I've read almost all her books.",
            "Can you recommend similar authors?"
        ],
        "expected_interests": ["reading", "books", "mystery", "Agatha Christie"],
        "expected_topics": ["reading", "books", "mystery novels", "Agatha Christie"]
    },
    {
        "name": "场景5：话题跳跃测试",
        "user_profile": None,
        "turns": [
            "I like playing basketball.",
            "But I also enjoy cooking.",
            "Actually, I'm learning to cook Italian food.",
            "Do you know how to make pasta?",
            "I want to try making pizza next."
        ],
        "expected_interests": ["basketball", "cooking", "Italian food"],
        "expected_topics": ["basketball", "cooking", "Italian food", "pasta", "pizza"]
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


def analyze_conversation_flow(conversation_history: list, current_turn: int) -> dict:
    """分析对话流畅度"""
    analysis = {
        "turn_count": current_turn,
        "topic_consistency": True,
        "response_relevance": True,
        "context_awareness": True,
        "issues": []
    }
    
    if len(conversation_history) < 2:
        return analysis
    
    # 检查话题一致性（AI是否在回应用户的话题）
    user_messages = [msg for msg in conversation_history if msg.get('role') == 'user']
    ai_messages = [msg for msg in conversation_history if msg.get('role') == 'assistant']
    
    if len(user_messages) >= 2 and len(ai_messages) >= 1:
        last_user_topic = extract_keywords(user_messages[-1].get('content', ''))
        prev_user_topic = extract_keywords(user_messages[-2].get('content', ''))
        ai_response = ai_messages[-1].get('content', '')
        
        # 检查AI是否回应了用户的话题
        if not any(keyword in ai_response.lower() for keyword in last_user_topic):
            analysis["response_relevance"] = False
            analysis["issues"].append(f"Turn {current_turn}: AI未回应用户话题")
        
        # 检查话题是否连贯
        if not any(keyword in last_user_topic for keyword in prev_user_topic):
            analysis["topic_consistency"] = False
            analysis["issues"].append(f"Turn {current_turn}: 话题跳跃")
    
    return analysis


def extract_keywords(text: str) -> list:
    """提取关键词"""
    import re
    # 简单的关键词提取（实际可以用更复杂的方法）
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    # 过滤常见词
    stop_words = {'this', 'that', 'with', 'from', 'about', 'have', 'want', 'like', 'very', 'really'}
    keywords = [w for w in words if w not in stop_words]
    return keywords[:5]  # 返回前5个关键词


def check_interest_capture(interests: list, expected_interests: list) -> dict:
    """检查兴趣捕捉"""
    analysis = {
        "captured_count": 0,
        "missing_interests": [],
        "capture_rate": 0.0
    }
    
    # 将期望的兴趣转为小写便于比较
    expected_lower = [i.lower() for i in expected_interests]
    captured_lower = [i.lower() for i in interests]
    
    # 检查每个期望兴趣是否被捕捉
    for expected in expected_lower:
        # 检查是否完全匹配或部分匹配
        found = False
        for captured in captured_lower:
            if expected in captured or captured in expected:
                found = True
                break
        
        if found:
            analysis["captured_count"] += 1
        else:
            analysis["missing_interests"].append(expected)
    
    if expected_interests:
        analysis["capture_rate"] = analysis["captured_count"] / len(expected_interests)
    
    return analysis


def main():
    """主测试函数"""
    print("=" * 100)
    print("qwen-omni 多轮对话质量测试")
    print("测试指标：对话流畅度、兴趣捕捉、上下文压缩时延")
    print("=" * 100)
    print()
    
    # 创建处理器
    processor = create_processor(service_type="qwen-omni")
    
    # 创建 TTS 服务
    print("初始化 TTS 服务...")
    tts_service = TTSServiceFactory.create(provider="openai")
    print("✅ TTS 服务初始化完成\n")
    
    all_results = []
    
    for scenario_idx, scenario in enumerate(CONVERSATION_SCENARIOS, 1):
        print(f"\n{'='*100}")
        print(f"场景 {scenario_idx}/{len(CONVERSATION_SCENARIOS)}: {scenario['name']}")
        print(f"{'='*100}\n")
        
        user_profile = scenario.get('user_profile')
        conversation_history = []
        all_interests = []
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
                
                # 2. 处理音频
                start_time = time.time()
                result = processor.process_audio(
                    audio_data=audio_data,
                    audio_format="mp3",
                    conversation_history=conversation_history,
                    user_profile=user_profile
                )
                process_time = time.time() - start_time
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
                all_interests.extend(new_interests)
                user_profile["interests"] = list(dict.fromkeys(all_interests))[-10:]  # 保留最近10个
                
                # 4. 更新对话历史
                conversation_history.append({
                    "role": "user",
                    "content": result.transcription or user_text
                })
                conversation_history.append({
                    "role": "assistant",
                    "content": result.full_response
                })
                
                # 5. 分析对话流畅度
                flow_analysis = analyze_conversation_flow(conversation_history, turn_idx)
                
                # 6. 显示结果
                print(f"AI回复: {result.full_response[:100]}...")
                print(f"转录: {result.transcription}")
                print(f"分数: {result.evaluation.get('overall_score', 0)} ({result.evaluation.get('cefr_level', '')})")
                print(f"处理时间: {process_time:.2f}s")
                print(f"兴趣: {new_interests}")
                
                if flow_analysis["issues"]:
                    print(f"⚠️  流畅度问题: {flow_analysis['issues']}")
                
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
                    "flow_analysis": flow_analysis
                })
                
            except Exception as e:
                print(f"❌ 处理失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 场景总结
        print(f"\n{'='*100}")
        print(f"场景总结: {scenario['name']}")
        print(f"{'='*100}")
        
        # 兴趣捕捉分析
        interest_analysis = check_interest_capture(
            list(dict.fromkeys(all_interests)),
            scenario['expected_interests']
        )
        
        print(f"\n兴趣捕捉:")
        print(f"  期望兴趣: {scenario['expected_interests']}")
        print(f"  实际捕捉: {list(dict.fromkeys(all_interests))}")
        print(f"  捕捉率: {interest_analysis['capture_rate']*100:.1f}% ({interest_analysis['captured_count']}/{len(scenario['expected_interests'])})")
        if interest_analysis['missing_interests']:
            print(f"  缺失兴趣: {interest_analysis['missing_interests']}")
        
        # 时延分析
        if turn_times:
            avg_time = sum(turn_times) / len(turn_times)
            max_time = max(turn_times)
            min_time = min(turn_times)
            print(f"\n处理时延:")
            print(f"  平均: {avg_time:.2f}s")
            print(f"  范围: {min_time:.2f}s - {max_time:.2f}s")
            print(f"  各轮: {[f'{t:.2f}s' for t in turn_times]}")
            
            # 检查上下文压缩（后几轮是否比前几轮慢）
            if len(turn_times) >= 3:
                first_half = sum(turn_times[:len(turn_times)//2]) / (len(turn_times)//2)
                second_half = sum(turn_times[len(turn_times)//2:]) / (len(turn_times) - len(turn_times)//2)
                compression_ratio = second_half / first_half if first_half > 0 else 1.0
                print(f"  上下文压缩影响: {compression_ratio:.2f}x (后{len(turn_times)//2}轮 vs 前{len(turn_times)//2}轮)")
        
        # 流畅度分析
        all_issues = []
        for tr in turn_results:
            if tr.get('flow_analysis', {}).get('issues'):
                all_issues.extend(tr['flow_analysis']['issues'])
        
        print(f"\n对话流畅度:")
        print(f"  总轮数: {len(scenario['turns'])}")
        print(f"  流畅度问题: {len(all_issues)}个")
        if all_issues:
            for issue in all_issues:
                print(f"    - {issue}")
        else:
            print(f"  ✅ 对话流畅，无问题")
        
        # 保存场景结果
        all_results.append({
            "scenario": scenario['name'],
            "turns": turn_results,
            "interest_analysis": interest_analysis,
            "timing_analysis": {
                "avg_time": avg_time if turn_times else 0,
                "max_time": max_time if turn_times else 0,
                "min_time": min_time if turn_times else 0,
                "all_times": turn_times
            },
            "flow_issues": all_issues,
            "final_interests": list(dict.fromkeys(all_interests))
        })
    
    # 保存所有结果
    output_file = "conversation_quality_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n\n{'='*100}")
    print("总体统计")
    print(f"{'='*100}")
    
    # 总体统计
    total_turns = sum(len(r['turns']) for r in all_results)
    total_interest_capture = sum(r['interest_analysis']['capture_rate'] for r in all_results) / len(all_results)
    all_times = []
    for r in all_results:
        all_times.extend(r['timing_analysis']['all_times'])
    total_flow_issues = sum(len(r['flow_issues']) for r in all_results)
    
    print(f"\n总体指标:")
    print(f"  总对话轮数: {total_turns}")
    print(f"  平均兴趣捕捉率: {total_interest_capture*100:.1f}%")
    print(f"  平均处理时延: {sum(all_times)/len(all_times):.2f}s" if all_times else "  平均处理时延: N/A")
    print(f"  流畅度问题总数: {total_flow_issues}")
    print(f"  流畅度问题率: {total_flow_issues/total_turns*100:.1f}%" if total_turns > 0 else "  流畅度问题率: N/A")
    
    print(f"\n结果已保存到: {output_file}")


if __name__ == "__main__":
    main()


