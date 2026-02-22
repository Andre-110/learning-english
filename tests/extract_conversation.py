#!/usr/bin/env python3
"""
对话提取脚本 - 提取对话内容和延迟指标

用法:
    python extract_conversation.py <json_file_or_dir> [--format markdown|text] [--output <output_file>]

示例:
    python extract_conversation.py results_new_prompt_20260201/v2_15turns/
    python extract_conversation.py results_new_prompt_20260201/v2_15turns/A1_15turns.json --format markdown
    python extract_conversation.py results_new_prompt_20260201/v2_15turns/ --output report.md
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


def load_conversation(file_path: str) -> Dict[str, Any]:
    """加载对话JSON文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_latency_stats(data: Dict[str, Any]) -> Dict[str, Any]:
    """提取延迟统计"""
    conversation = data.get('conversation', [])
    
    ai_latencies = []
    user_latencies = []
    user_word_counts = []
    
    for turn in conversation:
        latency = turn.get('latency_s', 0)
        if turn.get('role') == 'assistant':
            ai_latencies.append(latency)
        else:
            user_latencies.append(latency)
            if 'word_count' in turn:
                user_word_counts.append(turn['word_count'])
    
    def calc_stats(arr):
        if not arr:
            return {'avg': 0, 'min': 0, 'max': 0, 'total': 0}
        return {
            'avg': round(sum(arr) / len(arr), 3),
            'min': round(min(arr), 3),
            'max': round(max(arr), 3),
            'total': round(sum(arr), 3)
        }
    
    return {
        'ai_latency': calc_stats(ai_latencies),
        'user_latency': calc_stats(user_latencies),
        'user_word_count': calc_stats(user_word_counts),
        'total_turns': len(conversation),
        'ai_turns': len(ai_latencies),
        'user_turns': len(user_latencies)
    }


def format_conversation_text(data: Dict[str, Any]) -> str:
    """格式化对话为纯文本"""
    lines = []
    metadata = data.get('metadata', {})
    
    # 元信息
    lines.append(f"{'='*60}")
    lines.append(f"Level: {metadata.get('level', 'N/A')}")
    lines.append(f"Turns: {metadata.get('turns', 'N/A')}")
    lines.append(f"Timestamp: {metadata.get('timestamp', 'N/A')}")
    
    user_profile = metadata.get('user_profile', {})
    if user_profile:
        lines.append(f"User Interests: {', '.join(user_profile.get('interests', []))}")
    lines.append(f"{'='*60}\n")
    
    # 对话内容
    conversation = data.get('conversation', [])
    for turn in conversation:
        role = turn.get('role', 'unknown')
        content = turn.get('content', '')
        latency = turn.get('latency_s', 0)
        word_count = turn.get('word_count', '')
        
        role_label = '🤖 AI' if role == 'assistant' else '👤 User'
        
        # 延迟和词数信息
        info_parts = [f"{latency:.2f}s"]
        if word_count:
            info_parts.append(f"{word_count} words")
        info = f"[{', '.join(info_parts)}]"
        
        lines.append(f"{role_label} {info}")
        lines.append(f"{content}\n")
    
    # 延迟统计
    stats = extract_latency_stats(data)
    lines.append(f"{'='*60}")
    lines.append("📊 Latency Statistics")
    lines.append(f"{'='*60}")
    lines.append(f"AI Latency:   avg={stats['ai_latency']['avg']}s, min={stats['ai_latency']['min']}s, max={stats['ai_latency']['max']}s")
    lines.append(f"User Latency: avg={stats['user_latency']['avg']}s, min={stats['user_latency']['min']}s, max={stats['user_latency']['max']}s")
    if stats['user_word_count']['avg'] > 0:
        lines.append(f"User Words:   avg={stats['user_word_count']['avg']}, min={stats['user_word_count']['min']}, max={stats['user_word_count']['max']}")
    
    return '\n'.join(lines)


def format_conversation_markdown(data: Dict[str, Any]) -> str:
    """格式化对话为Markdown"""
    lines = []
    metadata = data.get('metadata', {})
    
    # 标题
    level = metadata.get('level', 'N/A')
    turns = metadata.get('turns', 'N/A')
    lines.append(f"# {level} - {turns} Turns Conversation\n")
    
    # 元信息
    lines.append("## Metadata\n")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Level | {level} |")
    lines.append(f"| Turns | {turns} |")
    lines.append(f"| Timestamp | {metadata.get('timestamp', 'N/A')} |")
    
    user_profile = metadata.get('user_profile', {})
    if user_profile:
        interests = ', '.join(user_profile.get('interests', []))
        lines.append(f"| User Interests | {interests} |")
    lines.append("")
    
    # 延迟统计
    stats = extract_latency_stats(data)
    lines.append("## Latency Statistics\n")
    lines.append("| Metric | Avg | Min | Max |")
    lines.append("|--------|-----|-----|-----|")
    lines.append(f"| AI Latency (s) | {stats['ai_latency']['avg']} | {stats['ai_latency']['min']} | {stats['ai_latency']['max']} |")
    lines.append(f"| User Latency (s) | {stats['user_latency']['avg']} | {stats['user_latency']['min']} | {stats['user_latency']['max']} |")
    if stats['user_word_count']['avg'] > 0:
        lines.append(f"| User Word Count | {stats['user_word_count']['avg']} | {stats['user_word_count']['min']} | {stats['user_word_count']['max']} |")
    lines.append("")
    
    # 对话内容
    lines.append("## Conversation\n")
    
    conversation = data.get('conversation', [])
    for i, turn in enumerate(conversation):
        role = turn.get('role', 'unknown')
        content = turn.get('content', '')
        latency = turn.get('latency_s', 0)
        word_count = turn.get('word_count', '')
        turn_num = turn.get('turn', i)
        
        role_emoji = '🤖' if role == 'assistant' else '👤'
        role_name = 'AI' if role == 'assistant' else 'User'
        
        # Turn header
        info_parts = [f"{latency:.2f}s"]
        if word_count:
            info_parts.append(f"{word_count} words")
        
        lines.append(f"### Turn {turn_num} - {role_emoji} {role_name} `{', '.join(info_parts)}`\n")
        lines.append(f"{content}\n")
    
    return '\n'.join(lines)


def format_summary_markdown(all_data: List[Dict[str, Any]]) -> str:
    """生成多文件汇总报告"""
    lines = []
    lines.append("# Conversation Analysis Summary\n")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 汇总表格
    lines.append("## Overview\n")
    lines.append("| Level | Turns | AI Avg Latency | User Avg Latency | User Avg Words |")
    lines.append("|-------|-------|----------------|------------------|----------------|")
    
    for item in all_data:
        data = item['data']
        metadata = data.get('metadata', {})
        stats = extract_latency_stats(data)
        
        level = metadata.get('level', 'N/A')
        turns = metadata.get('turns', 'N/A')
        ai_lat = stats['ai_latency']['avg']
        user_lat = stats['user_latency']['avg']
        user_words = stats['user_word_count']['avg']
        
        lines.append(f"| {level} | {turns} | {ai_lat}s | {user_lat}s | {user_words} |")
    
    lines.append("")
    
    # 每个对话的详细内容
    for item in all_data:
        lines.append("---\n")
        lines.append(format_conversation_markdown(item['data']))
    
    return '\n'.join(lines)


def process_file(file_path: str, fmt: str = 'text') -> str:
    """处理单个文件"""
    data = load_conversation(file_path)
    
    if fmt == 'markdown':
        return format_conversation_markdown(data)
    else:
        return format_conversation_text(data)


def process_directory(dir_path: str, fmt: str = 'markdown') -> str:
    """处理目录中的所有JSON文件"""
    all_data = []
    
    json_files = sorted(Path(dir_path).glob('*.json'))
    
    for json_file in json_files:
        try:
            data = load_conversation(str(json_file))
            all_data.append({
                'file': json_file.name,
                'data': data
            })
            print(f"✅ Loaded: {json_file.name}")
        except Exception as e:
            print(f"❌ Error loading {json_file.name}: {e}")
    
    if not all_data:
        return "No valid JSON files found."
    
    return format_summary_markdown(all_data)


def main():
    parser = argparse.ArgumentParser(description='提取对话内容和延迟指标')
    parser.add_argument('path', help='JSON文件或目录路径')
    parser.add_argument('--format', '-f', choices=['text', 'markdown'], default='markdown',
                        help='输出格式 (default: markdown)')
    parser.add_argument('--output', '-o', help='输出文件路径 (不指定则打印到终端)')
    
    args = parser.parse_args()
    
    path = args.path
    
    if os.path.isdir(path):
        result = process_directory(path, args.format)
    elif os.path.isfile(path):
        result = process_file(path, args.format)
    else:
        print(f"❌ Path not found: {path}")
        sys.exit(1)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"\n✅ Output saved to: {args.output}")
    else:
        print("\n" + result)


if __name__ == '__main__':
    main()
