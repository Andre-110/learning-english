"""
AI-to-AI 多轮对话测试 - 完整版（含热点内容注入）

测试完整系统功能：
- 真实 Prompt 模板
- 热点内容搜索与注入（OpenAI web_search）
- 节奏分析
- 对话历史管理
"""

import sys
import os
import json
import time
import random
from datetime import datetime
from collections import Counter
from typing import Dict, Any, List, Optional

# 添加项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 加载环境变量
env_path = os.path.join(project_root, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

# 导入系统组件
from services.llm import call_llm
from prompts.templates import (
    analyze_conversation_rhythm,
    get_pipeline_system_prompt,
    get_pipeline_user_prompt,
    get_pipeline_initial_prompt,
    get_pipeline_initial_prompt_with_content,
    get_content_injection_prompt,
    get_interest_extraction_prompt,
)

# 尝试导入热点内容服务
HOT_CONTENT_AVAILABLE = False
try:
    from services.content_injector import ContentInjector, get_content_injector
    from services.hot_content_pool import (
        create_hot_content_context,
        add_to_pool,
        select_best_hot_content,
        mark_used as mark_hot_content_used,
        get_pool_stats
    )
    HOT_CONTENT_AVAILABLE = True
    print("✅ 热点内容模块已加载")
except Exception as e:
    print(f"⚠️ 热点内容模块不可用: {e}")
    # 定义备用函数，避免 NameError
    def create_hot_content_context():
        return {
            "pool": [], "searched_topics": set(), "turn_count": 0,
            "last_inject_turn": -10, "inject_count": 0, "min_interval": 3, "max_inject": 5
        }
    def add_to_pool(*args, **kwargs): pass
    def select_best_hot_content(*args, **kwargs): return None
    def mark_hot_content_used(*args, **kwargs): pass
    def get_pool_stats(*args, **kwargs): return {}


# CEFR 等级对应的语言能力描述
LEVEL_DESCRIPTIONS = {
    'A1': 'very basic vocabulary, simple sentences, frequent grammar mistakes, may mix Chinese words',
    'A2': 'limited vocabulary, simple sentences, some grammar errors, occasional Chinese words',
    'B1': 'moderate vocabulary, compound sentences, occasional errors, mostly fluent',
    'B2': 'good vocabulary, complex sentences, few errors, fluent expression',
    'C1': 'advanced vocabulary, sophisticated sentences, rare errors, natural expression',
    'C2': 'near-native vocabulary, elegant sentences, essentially error-free'
}

# 话题检测 - 复用生产环境的 prompt
def detect_topics(text: str, user_interests: List[str], recent_context: str = "") -> List[str]:
    """
    使用生产环境的 Interest Extraction Prompt 检测用户话题
    
    复用 prompts/templates.py 中的 get_interest_extraction_prompt()
    """
    import json
    
    # 调用生产环境的 prompt
    prompt = get_interest_extraction_prompt(text, user_interests, recent_context)
    
    try:
        result = call_llm(
            system_prompt="You extract interests from user speech. Output ONLY a JSON array.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=50
        ).strip()
        
        # 解析 JSON 数组
        # 处理可能的格式问题（如 markdown 代码块）
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        result = result.strip()
        
        topics = json.loads(result)
        if isinstance(topics, list):
            return [t.lower() for t in topics if isinstance(t, str)]
        return []
    except json.JSONDecodeError:
        # 如果 JSON 解析失败，尝试简单解析
        if "[" in result and "]" in result:
            # 提取方括号内的内容
            inner = result[result.find("[")+1:result.find("]")]
            if inner.strip():
                return [t.strip().strip('"').strip("'").lower() for t in inner.split(",")]
        return []
    except Exception as e:
        print(f"     ⚠️ LLM 话题检测失败: {e}")
        return []


def simulate_user_response(ai_message: str, level: str, conversation_history: List[Dict]) -> str:
    """模拟用户回复 - 根据级别调整回复长度和风格"""
    ability = LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS['A2'])
    
    # 根据级别设置回复长度限制
    level_config = {
        'A1': {
            'max_words': '10-25 words',
            'max_tokens': 50,
            'style': 'Very short, simple sentences. Many pauses (um, uh). Often unsure. May use Chinese words.',
            'examples': '"I like... um... pizza." / "Yes, very good." / "I not sure..."'
        },
        'A2': {
            'max_words': '20-40 words', 
            'max_tokens': 70,
            'style': 'Short sentences. Some hesitation. Occasional Chinese words. Simple grammar.',
            'examples': '"I like cooking because... um, it is fun." / "Yes, I try it. It was good."'
        },
        'B1': {
            'max_words': '30-60 words',
            'max_tokens': 100,
            'style': 'Moderate length. Can express opinions. Some fillers. Mostly English.',
            'examples': '"I think cooking is relaxing. When I cook, I can... forget my stress."'
        },
        'B2': {
            'max_words': '40-80 words',
            'max_tokens': 120,
            'style': 'Natural flow. Can elaborate. Few errors. Occasional self-correction.',
            'examples': '"Thats interesting because I feel the same way about..."'
        },
        'C1': {
            'max_words': '50-100 words',
            'max_tokens': 150,
            'style': 'Fluent, sophisticated. Can discuss abstract ideas. Natural pauses for thought.',
            'examples': '"That raises an interesting point about how we perceive..."'
        },
        'C2': {
            'max_words': '60-120 words',
            'max_tokens': 180,
            'style': 'Near-native. Nuanced expression. Idiomatic.',
            'examples': '"Its funny you mention that - I was just thinking about..."'
        }
    }
    
    config = level_config.get(level, level_config['A2'])
    
    context = ""
    if conversation_history:
        recent = conversation_history[-4:]
        for msg in recent:
            role = "Tutor" if msg.get('role') == 'assistant' else "You"
            content = msg.get('content', '')[:100]
            context += f"{role}: {content}\n"
    
    prompt = f'''You are an English learner at {level} level practicing with a tutor.

YOUR ABILITY: {ability}

CRITICAL - RESPONSE LENGTH: {config['max_words']} (NOT MORE!)
STYLE: {config['style']}
EXAMPLE: {config['examples']}

Previous conversation:
{context}

The tutor just said: "{ai_message}"

RULES:
1. Stay within {config['max_words']} - this is VERY important
2. Lower levels (A1/A2) should give SHORT answers, not essays
3. Include hesitation markers (um, uh, ...) naturally
4. Sometimes just give a simple answer without elaborating
5. Dont always ask questions back - real learners often dont

Your response (no quotes):'''

    return call_llm(
        system_prompt=f"You simulate a {level} English learner. Keep responses SHORT for beginners.",
        user_prompt=prompt,
        temperature=0.8,
        max_tokens=config['max_tokens']
    )


def run_conversation(
    num_turns: int = 20, 
    level: str = 'A2', 
    output_file: str = None,
    enable_hot_content: bool = True
):
    """运行多轮对话测试（含热点内容注入）"""
    
    # 用户画像
    all_interests = ['movies', 'music', 'travel', 'sports', 'cooking', 'reading', 'technology', 'art']
    user_profile = {
        'cefr_level': level,
        'interests': random.sample(all_interests, 3),
        'overall_score': 50,
        'strengths': [],
        'weaknesses': []
    }
    
    # 输出路径
    if output_file is None:
        suffix = '_hot' if enable_hot_content and HOT_CONTENT_AVAILABLE else ''
        output_path = os.path.join(project_root, 'tests', f'ai_{level}_{num_turns}turns{suffix}.json')
    else:
        output_path = output_file if os.path.isabs(output_file) else os.path.join(project_root, output_file)
    
    # 🆕 使用共享模块创建热点上下文（与生产代码一致）
    hot_context = create_hot_content_context()
    hot_context['greeting_content'] = None  # 测试专用字段
    
    use_hot = enable_hot_content and HOT_CONTENT_AVAILABLE
    
    print('='*70)
    print(f'AI-to-AI 对话测试 | 等级: {level} | 轮次: {num_turns}')
    print(f'用户兴趣: {user_profile["interests"]}')
    print(f'热点功能: {"✅ 启用" if use_hot else "❌ 禁用"}')
    print('='*70)
    
    # 数据收集
    conversation_log = []
    metrics = {
        'ai_latencies': [],
        'user_latencies': [],
        'strategies': [],
        'hot_content_events': [],
    }
    conversation_history = []
    
    # ========== 生成初始问题（可能包含热点）==========
    print('\n生成初始问题...')
    hot_content_dict = None
    
    if use_hot:
        print('  🔥 搜索开场白热点...')
        try:
            injector = get_content_injector()
            hot_content = injector.fetch_for_greeting(user_profile)
            if hot_content:
                hot_content_dict = {
                    'topic': hot_content.topic,
                    'headline': hot_content.headline,
                    'detail': hot_content.detail,
                }
                hot_context['greeting_content'] = hot_content_dict
                # 🆕 将开场白话题加入已搜索集合，防止后续重复
                hot_context['searched_topics'].add(hot_content.topic.lower())
                # 🆕 将开场白热点加入池并标记已使用
                hot_context['pool'].append({
                    'topic': hot_content.topic,
                    'headline': hot_content.headline,
                    'detail': hot_content.detail,
                    'search_turn': 0,
                    'used': True
                })
                hot_context['inject_count'] = 1
                hot_context['last_inject_turn'] = 0
                print(f'  ✅ 热点话题: {hot_content.topic}')
                print(f'  📰 {hot_content.headline}')
                metrics['hot_content_events'].append({
                    'turn': 0,
                    'type': 'greeting',
                    'topic': hot_content.topic,
                    'headline': hot_content.headline,
                })
            else:
                print('  ⚠️ 未获取到热点，使用普通开场白')
        except Exception as e:
            print(f'  ❌ 热点获取失败: {e}')
    
    start = time.time()
    
    if hot_content_dict:
        initial_prompt = get_pipeline_initial_prompt_with_content(user_profile, hot_content_dict)
    else:
        initial_prompt = get_pipeline_initial_prompt(user_profile)
    
    ai_response = call_llm(
        system_prompt=initial_prompt,
        user_prompt="Generate an engaging opening question for this student.",
        temperature=0.8,
        max_tokens=150
    )
    
    latency = time.time() - start
    print(f'\n[Turn 0] 🤖 AI: {ai_response}')
    print(f'         ⏱️ {latency:.2f}s')
    if hot_content_dict:
        print(f'         🔥 包含热点: {hot_content_dict["topic"]}')
    
    conversation_history.append({'role': 'assistant', 'content': ai_response})
    conversation_log.append({
        'turn': 0,
        'role': 'assistant',
        'content': ai_response,
        'latency_s': round(latency, 3),
        'has_hot_content': hot_content_dict is not None,
        'hot_topic': hot_content_dict.get('topic') if hot_content_dict else None,
    })
    
    # ========== 多轮对话 ==========
    for turn in range(1, num_turns + 1):
        print(f'\n[Turn {turn}]')
        
        # 1. 模拟用户回复
        start = time.time()
        user_response = simulate_user_response(ai_response, level, conversation_history)
        user_latency = time.time() - start
        
        print(f'  👤 User: {user_response}')
        print(f'     ⏱️ {user_latency:.2f}s')
        
        metrics['user_latencies'].append(user_latency)
        conversation_history.append({'role': 'user', 'content': user_response})
        
        # 2. 节奏分析
        rhythm = analyze_conversation_rhythm(conversation_history)
        strategy = rhythm.get('suggested_strategy', 'continue')
        rhythm_instruction = rhythm.get('rhythm_instruction', '')
        metrics['strategies'].append(strategy)
        
        # 3. 被动触发热点检测（使用热点池）
        if use_hot and hot_context['inject_count'] < hot_context.get('max_inject', 5):
            # 构建上下文
            recent_context = "\n".join([
                f"{m.get('role', 'user')}: {m.get('content', '')[:80]}" 
                for m in conversation_history[-4:]
            ])
            detected_topics = detect_topics(user_response, user_profile['interests'], recent_context)
            
            if detected_topics:
                new_topic = detected_topics[0]
                
                # 🆕 简化条件：只检查是否已搜索过
                if new_topic not in hot_context['searched_topics']:
                    print(f'     🔍 检测到新话题: {new_topic}，后台搜索...')
                    hot_context['searched_topics'].add(new_topic)
                    
                    # 后台搜索，加入热点池
                    import threading
                    def background_search():
                        try:
                            injector = get_content_injector()
                            topic_content = injector.fetch_for_topic(new_topic, level)
                            if topic_content:
                                # 🆕 使用共享模块加入热点池
                                add_to_pool(
                                    hot_context,
                                    topic=topic_content.topic,
                                    headline=topic_content.headline,
                                    detail=topic_content.detail,
                                    search_turn=turn
                                )
                                print(f'     ✅ 热点入池: {topic_content.headline[:40]}...')
                                # 🆕 事件类型改为 'search'，表示搜索入池
                                metrics['hot_content_events'].append({
                                    'turn': turn,
                                    'type': 'search',  # 搜索入池事件
                                    'topic': new_topic,
                                    'headline': topic_content.headline,
                                })
                        except Exception as e:
                            print(f'     ⚠️ 热点搜索失败: {e}')
                    
                    threading.Thread(target=background_search, daemon=True).start()
                else:
                    print(f'     ⏭️ 话题已搜索过: {new_topic}')
        
        conversation_log.append({
            'turn': turn,
            'role': 'user',
            'content': user_response,
            'latency_s': round(user_latency, 3),
            'word_count': len(user_response.split()),
            'strategy': strategy,
        })
        
        # 4. AI 回复（可能包含热点注入）
        start = time.time()
        
        system_prompt = get_pipeline_system_prompt(user_profile)
        
        # 🆕 使用共享模块选择最佳热点
        hot_context['turn_count'] = turn  # 更新轮次
        selected_hot = select_best_hot_content(hot_context, conversation_history, turn)
        
        if selected_hot:
            # 使用热点注入 prompt
            context = "\n".join([
                f"{m.get('role', 'user')}: {m.get('content', '')[:100]}" 
                for m in conversation_history[-6:]
            ])
            user_prompt = get_content_injection_prompt(selected_hot, context, level)
            
            # 🆕 使用共享模块标记热点已使用
            mark_hot_content_used(hot_context, selected_hot, turn)
            print(f'     🔥 热点注入: {selected_hot.get("topic", "")} (第 {hot_context["inject_count"]} 次)')
        else:
            user_prompt = get_pipeline_user_prompt(user_response, conversation_history)
            if rhythm_instruction:
                user_prompt = f"{rhythm_instruction}\n\n{user_prompt}"
        
        ai_response = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=200
        )
        
        ai_latency = time.time() - start
        print(f'  🤖 AI: {ai_response}')
        print(f'     ⏱️ {ai_latency:.2f}s | 策略: {strategy}')
        
        metrics['ai_latencies'].append(ai_latency)
        conversation_history.append({'role': 'assistant', 'content': ai_response})
        
        # 🆕 记录实际注入事件
        if selected_hot:
            metrics['hot_content_events'].append({
                'turn': turn,
                'type': 'inject',  # 实际注入事件
                'topic': selected_hot.get('topic'),
                'headline': selected_hot.get('headline'),
            })
        
        conversation_log.append({
            'turn': turn,
            'role': 'assistant',
            'content': ai_response,
            'latency_s': round(ai_latency, 3),
            'strategy': strategy,
            'has_hot_content': selected_hot is not None,
            'hot_topic': selected_hot.get('topic') if selected_hot else None,
        })
    
    # ========== 统计 ==========
    print('\n' + '='*70)
    print('统计')
    print('='*70)
    print(f'AI 延迟: 平均 {sum(metrics["ai_latencies"])/len(metrics["ai_latencies"]):.2f}s')
    print(f'User 延迟: 平均 {sum(metrics["user_latencies"])/len(metrics["user_latencies"]):.2f}s')
    print(f'策略分布: {dict(Counter(metrics["strategies"]))}')
    
    if metrics['hot_content_events']:
        # 🆕 分类统计
        greetings = [e for e in metrics['hot_content_events'] if e['type'] == 'greeting']
        searches = [e for e in metrics['hot_content_events'] if e['type'] == 'search']
        injects = [e for e in metrics['hot_content_events'] if e['type'] == 'inject']
        
        print(f'\n🔥 热点统计:')
        print(f'  开场白: {len(greetings)} 次')
        print(f'  搜索入池: {len(searches)} 次')
        print(f'  实际注入: {len(injects)} 次')
        
        if greetings:
            print(f'\n  📢 开场白:')
            for e in greetings:
                print(f'     Turn {e["turn"]}: {e["topic"]}')
        
        if injects:
            print(f'\n  💉 注入事件:')
            for e in injects:
                print(f'     Turn {e["turn"]}: {e["topic"]}')
    
    # 保存
    output = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'turns': num_turns,
            'user_profile': user_profile,
            'hot_content_enabled': use_hot,
        },
        'summary': {
            'ai_avg_latency': round(sum(metrics['ai_latencies'])/len(metrics['ai_latencies']), 3),
            'user_avg_latency': round(sum(metrics['user_latencies'])/len(metrics['user_latencies']), 3),
            'strategies': dict(Counter(metrics['strategies'])),
            'hot_content_events': len(metrics['hot_content_events']),
        },
        'hot_content_events': metrics['hot_content_events'],
        'conversation': conversation_log,
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f'\n✅ 保存到 {output_path}')
    return output


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='AI-to-AI 多轮对话测试（含热点内容）')
    parser.add_argument('--level', default='A2', help='CEFR 等级')
    parser.add_argument('--turns', type=int, default=20, help='对话轮次')
    parser.add_argument('--output', default=None, help='输出文件路径')
    parser.add_argument('--no-hot', action='store_true', help='禁用热点内容功能')
    args = parser.parse_args()
    
    run_conversation(args.turns, args.level, args.output, enable_hot_content=not args.no_hot)
