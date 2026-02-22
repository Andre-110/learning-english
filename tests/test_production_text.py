"""
生产环境文本对话测试 - 直接调用生产模块

测试完整生产流程：
- GPT4oPipeline.chat() - 核心对话
- GPT4oPipeline.generate_initial_question_with_content() - 带热点开场白
- GPT4oPipeline.generate_response_with_content() - 带热点回复
- ContentInjector - 异步热点搜索
"""

import sys
import os
import json
import time
import asyncio
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

# 导入生产环境模块
from services.gpt4o_pipeline import GPT4oPipeline, create_gpt4o_pipeline
from services.content_injector import ContentInjector, get_content_injector
from services.user_simulator import create_user_simulator

print("✅ 生产模块已加载")


def run_production_test(
    num_turns: int = 20,
    level: str = 'A2',
    output_file: str = None
):
    """
    使用生产模块运行多轮对话测试
    """
    
    # 创建生产环境实例
    pipeline = create_gpt4o_pipeline()
    injector = get_content_injector()
    user_sim = create_user_simulator(level)
    
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
        output_path = os.path.join(project_root, 'tests', f'prod_{level}_{num_turns}turns.json')
    else:
        output_path = output_file if os.path.isabs(output_file) else os.path.join(project_root, output_file)
    
    print('='*70)
    print(f'生产环境测试 | 等级: {level} | 轮次: {num_turns}')
    print(f'用户兴趣: {user_profile["interests"]}')
    print('='*70)
    
    # 数据收集
    conversation_log = []
    metrics = {
        'ai_latencies': [],
        'user_latencies': [],
        'hot_search_latencies': [],
        'hot_content_events': [],
    }
    conversation_history = []
    
    # 热点上下文（模拟生产环境的异步热点）
    hot_context = {
        'pending': None,
        'last_topic': None,
        'injected_count': 0,
        'max_injections': 3,
    }
    
    # ========== 1. 开场白（带热点）==========
    print('\n[Turn 0] 生成开场白...')
    
    # 异步获取热点（生产环境用 asyncio.wait_for 限时）
    hot_content_dict = None
    hot_search_start = time.time()
    
    try:
        hot_content = injector.fetch_for_greeting(user_profile)
        hot_search_time = time.time() - hot_search_start
        
        if hot_content:
            hot_content_dict = {
                'topic': hot_content.topic,
                'headline': hot_content.headline,
                'detail': hot_content.detail,
            }
            print(f'  🔥 热点话题: {hot_content.topic} ({hot_search_time:.2f}s)')
            print(f'  📰 {hot_content.headline}')
            metrics['hot_search_latencies'].append(hot_search_time)
            metrics['hot_content_events'].append({
                'turn': 0,
                'type': 'greeting',
                'topic': hot_content.topic,
                'headline': hot_content.headline,
                'search_time': round(hot_search_time, 2),
            })
    except Exception as e:
        print(f'  ⚠️ 热点获取失败: {e}')
    
    # 生成开场白（使用生产环境的 generate_initial_question_with_content）
    ai_start = time.time()
    ai_response = ""
    
    for chunk in pipeline.generate_initial_question_with_content(user_profile, hot_content_dict):
        chunk_type = chunk.get('type')
        if chunk_type == 'text_chunk':
            ai_response += chunk.get('text', '')
        elif chunk_type == 'done':
            break
    
    ai_latency = time.time() - ai_start
    print(f'  🤖 AI: {ai_response}')
    print(f'  ⏱️ AI延迟: {ai_latency:.2f}s')
    
    conversation_history.append({'role': 'assistant', 'content': ai_response})
    conversation_log.append({
        'turn': 0,
        'role': 'assistant',
        'content': ai_response,
        'latency_s': round(ai_latency, 3),
        'has_hot_content': hot_content_dict is not None,
        'hot_topic': hot_content_dict.get('topic') if hot_content_dict else None,
    })
    
    # ========== 2. 多轮对话 ==========
    for turn in range(1, num_turns + 1):
        print(f'\n[Turn {turn}]')
        
        # 2.1 模拟用户回复（使用生产环境的 UserSimulator）
        user_start = time.time()
        user_response = user_sim.respond(ai_response, conversation_history)
        user_latency = time.time() - user_start
        
        print(f'  👤 User: {user_response}')
        print(f'  ⏱️ User延迟: {user_latency:.2f}s')
        
        metrics['user_latencies'].append(user_latency)
        conversation_history.append({'role': 'user', 'content': user_response})
        
        conversation_log.append({
            'turn': turn,
            'role': 'user',
            'content': user_response,
            'latency_s': round(user_latency, 3),
            'word_count': len(user_response.split()),
        })
        
        # 2.2 检测话题，异步搜索热点（真正的异步，不阻塞 AI 回复）
        # 生产环境：asyncio.create_task(search_async()) 启动后立即继续
        # 这里用线程模拟异步：搜索在后台进行，结果在下一轮使用
        
        if hot_context['injected_count'] < hot_context['max_injections']:
            detected_topic = None
            for interest in user_profile['interests']:
                if interest.lower() in user_response.lower():
                    detected_topic = interest
                    break
            
            if detected_topic and detected_topic != hot_context['last_topic']:
                print(f'  🔍 检测到话题: {detected_topic}，后台搜索热点...')
                hot_context['last_topic'] = detected_topic
                
                # 启动后台搜索（不阻塞）
                import threading
                def async_search():
                    try:
                        search_start = time.time()
                        topic_content = injector.fetch_for_topic(detected_topic, level)
                        search_time = time.time() - search_start
                        
                        if topic_content:
                            hot_context['pending'] = {
                                'topic': topic_content.topic,
                                'headline': topic_content.headline,
                                'detail': topic_content.detail,
                            }
                            hot_context['injected_count'] += 1
                            metrics['hot_search_latencies'].append(search_time)
                            metrics['hot_content_events'].append({
                                'turn': turn,
                                'type': 'async_search',
                                'topic': detected_topic,
                                'headline': topic_content.headline,
                                'search_time': round(search_time, 2),
                            })
                            print(f'  [后台] ✅ 热点就绪: {topic_content.headline[:40]}... ({search_time:.2f}s)')
                    except Exception as e:
                        print(f'  [后台] ⚠️ 热点搜索失败: {e}')
                
                threading.Thread(target=async_search, daemon=True).start()
        
        # 2.3 AI 回复（使用生产环境的 chat 或 generate_response_with_content）
        ai_start = time.time()
        ai_response = ""
        used_hot = False
        
        # 如果有待注入的热点，使用 generate_response_with_content
        if hot_context.get('pending'):
            pending_hot = hot_context['pending']
            hot_context['pending'] = None  # 清除
            
            for chunk in pipeline.generate_response_with_content(
                user_text=user_response,
                hot_content=pending_hot,
                conversation_history=conversation_history,
                user_profile=user_profile
            ):
                chunk_type = chunk.get('type')
                if chunk_type == 'text_chunk':
                    ai_response += chunk.get('text', '')
                elif chunk_type == 'done':
                    break
            used_hot = True
        else:
            # 普通对话（只测试 LLM，跳过 TTS）
            # 生产环境用 process_text 包含 TTS，这里只测 LLM 核心逻辑
            for text_chunk in pipeline.chat(
                user_text=user_response,
                conversation_history=conversation_history,
                user_profile=user_profile,
                stream=True
            ):
                ai_response += text_chunk
        
        ai_latency = time.time() - ai_start
        metrics['ai_latencies'].append(ai_latency)
        
        print(f'  🤖 AI: {ai_response}')
        print(f'  ⏱️ AI延迟: {ai_latency:.2f}s', end='')
        if used_hot:
            print(f' 🔥[{pending_hot["topic"]}]')
        else:
            print()
        
        conversation_history.append({'role': 'assistant', 'content': ai_response})
        conversation_log.append({
            'turn': turn,
            'role': 'assistant',
            'content': ai_response,
            'latency_s': round(ai_latency, 3),
            'has_hot_content': used_hot,
            'hot_topic': pending_hot.get('topic') if used_hot else None,
        })
    
    # ========== 统计 ==========
    print('\n' + '='*70)
    print('统计')
    print('='*70)
    
    ai_avg = sum(metrics['ai_latencies']) / len(metrics['ai_latencies'])
    user_avg = sum(metrics['user_latencies']) / len(metrics['user_latencies'])
    
    print(f'AI 平均延迟: {ai_avg:.2f}s')
    print(f'User 平均延迟: {user_avg:.2f}s')
    
    if metrics['hot_search_latencies']:
        hot_avg = sum(metrics['hot_search_latencies']) / len(metrics['hot_search_latencies'])
        print(f'热点搜索平均延迟: {hot_avg:.2f}s')
    
    if metrics['hot_content_events']:
        print(f'\n🔥 热点注入事件:')
        for event in metrics['hot_content_events']:
            print(f'  - Turn {event["turn"]}: [{event["type"]}] {event["topic"]} ({event["search_time"]}s)')
    
    # 保存
    output = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'turns': num_turns,
            'user_profile': user_profile,
            'test_type': 'production_modules',
        },
        'summary': {
            'ai_avg_latency': round(ai_avg, 3),
            'user_avg_latency': round(user_avg, 3),
            'hot_search_avg_latency': round(sum(metrics['hot_search_latencies']) / len(metrics['hot_search_latencies']), 3) if metrics['hot_search_latencies'] else 0,
            'hot_content_events': len(metrics['hot_content_events']),
        },
        'hot_content_events': metrics['hot_content_events'],
        'conversation': conversation_log,
    }
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f'\n✅ 保存到 {output_path}')
    return output


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='生产环境文本对话测试')
    parser.add_argument('--level', default='A2', help='CEFR 等级')
    parser.add_argument('--turns', type=int, default=20, help='对话轮次')
    parser.add_argument('--output', default=None, help='输出文件路径')
    args = parser.parse_args()
    
    run_production_test(args.turns, args.level, args.output)
