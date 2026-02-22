#!/usr/bin/env python3
"""
从测试日志中提取关键信息：对话输入、输出、评分和总结报告
"""
import sys
import re
import os
from datetime import datetime
from typing import List, Dict, Optional

def extract_conversation_data(log_content: str) -> Dict:
    """从日志内容中提取对话数据"""
    result = {
        'config': {},
        'conversations': [],
        'summary': {}
    }
    
    lines = log_content.split('\n')
    
    # 提取配置信息
    for i, line in enumerate(lines):
        if 'SPEECH_PROVIDER:' in line:
            result['config']['speech_provider'] = line.split('SPEECH_PROVIDER:')[1].strip()
        elif 'FUNASR_MODEL_NAME:' in line:
            result['config']['funasr_model'] = line.split('FUNASR_MODEL_NAME:')[1].strip()
        elif '对话ID:' in line:
            result['config']['conversation_id'] = line.split('对话ID:')[1].strip()
    
    # 提取每轮对话信息
    current_round = None
    current_data = {}
    current_test_scenario = None  # 当前测试场景
    
    for i, line in enumerate(lines):
        # 检测测试场景（格式: "测试X: 场景名称"）- 必须在检测新轮次之前
        test_scenario_match = re.search(r'测试\d+:\s*(.+)', line)
        if test_scenario_match:
            current_test_scenario = test_scenario_match.group(1).strip()
        
        # 检测新的一轮对话（支持多种格式）
        # 格式1: "第 1 轮对话"
        # 格式2: "--- 第 1 轮对话 ---"
        # 格式3: "第1轮对话..."
        is_new_round = False
        if '--- 第' in line and '轮对话 ---' in line:
            is_new_round = True
        elif '第' in line and '轮对话' in line and not line.strip().startswith('第') or ('第' in line and '轮' in line and '对话' in line):
            # 避免匹配到"第1轮对话..."这种格式
            if not ('第' in line and '轮对话...' in line):
                is_new_round = True
        
        if is_new_round:
            # 保存上一轮数据
            if current_round is not None and current_data:
                # 只有当有实际内容时才保存
                if current_data.get('transcribed_text') or current_data.get('score') is not None:
                    # 添加测试场景信息
                    current_data['test_scenario'] = current_test_scenario
                    result['conversations'].append(current_data.copy())
            
            # 提取轮次号（支持多种格式）
            match = re.search(r'第\s*(\d+)\s*轮', line)
            if match:
                current_round = int(match.group(1))
                current_data = {
                    'round': current_round,
                    'audio_file': '',
                    'transcribed_text': '',
                    'score': None,
                    'cefr_level': '',
                    'strengths': [],
                    'weaknesses': [],
                    'next_question': '',
                    'transcription_time': None,
                    'evaluation_time': None
                }
                
                # 立即检查下一行是否有音频文件信息
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if '📤 使用音频文件:' in next_line:
                        current_data['audio_file'] = next_line.split('📤 使用音频文件:')[1].strip()
                    elif '📤 音频文件:' in next_line:
                        current_data['audio_file'] = next_line.split('📤 音频文件:')[1].strip()
                    elif re.search(r'test_\w+\.mp3', next_line):
                        match_audio = re.search(r'(test_\w+\.mp3)', next_line)
                        if match_audio:
                            current_data['audio_file'] = match_audio.group(1)
        
        # 提取音频文件名（支持多种格式）
        if current_round:
            if '📤 音频文件:' in line:
                current_data['audio_file'] = line.split('📤 音频文件:')[1].strip()
            elif '📤 使用音频文件:' in line:
                current_data['audio_file'] = line.split('📤 使用音频文件:')[1].strip()
            # 检查行中是否包含音频文件名（如 test_simple.mp3）
            elif re.search(r'test_\w+\.mp3', line) and not current_data['audio_file']:
                match = re.search(r'(test_\w+\.mp3)', line)
                if match:
                    current_data['audio_file'] = match.group(1)
            # 如果当前行是"--- 第 X 轮对话 ---"的下一行，检查是否有音频文件
            elif i > 0 and '--- 第' in lines[i-1] and '轮对话 ---' in lines[i-1]:
                if '📤 使用音频文件:' in line:
                    current_data['audio_file'] = line.split('📤 使用音频文件:')[1].strip()
                elif re.search(r'test_\w+\.mp3', line):
                    match = re.search(r'(test_\w+\.mp3)', line)
                    if match:
                        current_data['audio_file'] = match.group(1)
        
        # 提取转录文本（支持多种格式）
        if current_round:
            if '📝 转录文本:' in line:
                current_data['transcribed_text'] = line.split('📝 转录文本:')[1].strip()
            elif '📝 用户输入（转录）:' in line:
                current_data['transcribed_text'] = line.split('📝 用户输入（转录）:')[1].strip()
            elif '用户回答:' in line and not current_data['transcribed_text']:
                # 格式: "用户回答: ..."
                current_data['transcribed_text'] = line.split('用户回答:')[1].strip()
        
        # 从日志INFO行中提取评估信息（格式: "evaluate] OUTPUT: score=32.25, level=A2"）
        if current_round and current_data['score'] is None:
            if 'evaluate] OUTPUT:' in line or 'Evaluation completed:' in line:
                # 提取分数
                score_match = re.search(r'score=(\d+\.?\d*)', line)
                if score_match:
                    current_data['score'] = float(score_match.group(1))
                # 提取CEFR等级
                level_match = re.search(r'level=([A-C][12])', line)
                if level_match:
                    current_data['cefr_level'] = level_match.group(1)
        
        # 提取分数（支持多种格式）
        if current_round and current_data['score'] is None:
            # 格式1: "📊 综合分数: 32.2/100"
            # 格式2: "综合分数: 32.2/100"
            # 格式3: "分数: 28.2/100 | CEFR: A1"
            # 格式4: "   分数: 28.2/100 | CEFR: A1"
            # 格式5: "✅ 评估完成\n   综合分数: 32.2/100\n   CEFR等级: A2" (多行格式)
            score_match = re.search(r'(\d+\.?\d*)/100', line)
            if score_match:
                # 检查是否在评估相关的上下文中
                if ('分数' in line or 'score' in line.lower() or 
                    '评估完成' in line or '评估' in line or
                    '综合' in line):
                    current_data['score'] = float(score_match.group(1))
                    # 如果同一行有CEFR等级，也提取
                    if 'CEFR:' in line:
                        level_match = re.search(r'CEFR:\s*([A-C][12])', line)
                        if level_match:
                            current_data['cefr_level'] = level_match.group(1)
        
        # 如果当前行是"✅ 评估完成"，检查后续行是否有分数和CEFR等级
        if current_round and '✅ 评估完成' in line and current_data['score'] is None:
            # 检查后续2行
            for j in range(i + 1, min(i + 3, len(lines))):
                next_line = lines[j]
                # 提取分数
                if current_data['score'] is None:
                    score_match = re.search(r'(\d+\.?\d*)/100', next_line)
                    if score_match and ('综合分数' in next_line or '分数' in next_line):
                        current_data['score'] = float(score_match.group(1))
                # 提取CEFR等级
                if not current_data['cefr_level']:
                    if 'CEFR等级:' in next_line:
                        level_match = re.search(r'CEFR等级?:\s*([A-C][12])', next_line)
                        if level_match:
                            current_data['cefr_level'] = level_match.group(1)
                    elif 'CEFR:' in next_line:
                        level_match = re.search(r'CEFR:\s*([A-C][12])', next_line)
                        if level_match:
                            current_data['cefr_level'] = level_match.group(1)
        
        # 提取CEFR等级（支持多种格式）
        if current_round and not current_data['cefr_level']:
            # 格式1: "🎯 CEFR等级: B1"
            if '🎯 CEFR等级:' in line:
                current_data['cefr_level'] = line.split('🎯 CEFR等级:')[1].strip()
            # 格式2: "CEFR等级: A2"
            elif 'CEFR等级:' in line:
                level_match = re.search(r'CEFR等级?:\s*([A-C][12])', line)
                if level_match:
                    current_data['cefr_level'] = level_match.group(1)
            # 格式3: "CEFR: A1" 或 "| CEFR: A1" (在同一行)
            elif 'CEFR:' in line:
                level_match = re.search(r'CEFR:\s*([A-C][12])', line)
                if level_match:
                    current_data['cefr_level'] = level_match.group(1)
            # 格式4: 如果当前行有分数，检查下一行是否有CEFR
            elif current_data['score'] is not None and i < len(lines) - 1:
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if 'CEFR' in next_line:
                    level_match = re.search(r'CEFR[等级]?:\s*([A-C][12])', next_line)
                    if level_match:
                        current_data['cefr_level'] = level_match.group(1)
            # 格式5: 检查前一行是否有分数，当前行有CEFR
            elif i > 0 and 'CEFR' in line:
                prev_line = lines[i - 1] if i > 0 else ""
                if re.search(r'\d+\.?\d*/100', prev_line):
                    level_match = re.search(r'CEFR[等级]?:\s*([A-C][12])', line)
                    if level_match:
                        current_data['cefr_level'] = level_match.group(1)
        
        # 提取强项（支持多种格式）
        if current_round:
            if '💪 强项:' in line:
                strengths_str = line.split('💪 强项:')[1].strip()
                if strengths_str and strengths_str != '无':
                    current_data['strengths'] = [s.strip() for s in strengths_str.split(',')]
            elif '强项:' in line and '弱项' not in line:
                strengths_str = line.split('强项:')[1].split('弱项')[0].strip() if '弱项' in line else line.split('强项:')[1].strip()
                if strengths_str and strengths_str != '无':
                    current_data['strengths'] = [s.strip() for s in strengths_str.split(',')]
            # 从ability_profile中提取强项（JSON格式）
            elif "'strengths':" in line or '"strengths":' in line:
                strengths_match = re.search(r"strengths['\"]?\s*:\s*\[(.*?)\]", line)
                if strengths_match:
                    strengths_str = strengths_match.group(1)
                    if strengths_str:
                        strengths_list = [s.strip().strip("'\"") for s in strengths_str.split(',')]
                        current_data['strengths'] = [s for s in strengths_list if s]
        
        # 提取弱项（支持多种格式）
        if current_round:
            if '⚠️  弱项:' in line:
                weaknesses_str = line.split('⚠️  弱项:')[1].strip()
                if weaknesses_str and weaknesses_str != '无':
                    current_data['weaknesses'] = [w.strip() for w in weaknesses_str.split(',')]
            elif '弱项:' in line:
                weaknesses_str = line.split('弱项:')[1].strip()
                if weaknesses_str and weaknesses_str != '无':
                    current_data['weaknesses'] = [w.strip() for w in weaknesses_str.split(',')]
            # 从ability_profile中提取弱项（JSON格式）
            elif "'weaknesses':" in line or '"weaknesses":' in line:
                weaknesses_match = re.search(r"weaknesses['\"]?\s*:\s*\[(.*?)\]", line)
                if weaknesses_match:
                    weaknesses_str = weaknesses_match.group(1)
                    if weaknesses_str:
                        weaknesses_list = [w.strip().strip("'\"") for w in weaknesses_str.split(',')]
                        current_data['weaknesses'] = [w for w in weaknesses_list if w]
        
        # 提取下一题（支持多种格式）
        if current_round:
            if '❓ 下一题:' in line:
                current_data['next_question'] = line.split('❓ 下一题:')[1].strip()
            elif '下一题:' in line:
                current_data['next_question'] = line.split('下一题:')[1].strip()
            elif '系统问题:' in line:
                current_data['next_question'] = line.split('系统问题:')[1].strip()
        
        # 提取转录耗时（从"✅ 转录成功 (耗时: X.XX秒)"或"转录耗时: X.XXs"）
        if current_round:
            if '✅ 转录成功 (耗时:' in line:
                time_match = re.search(r'耗时:\s*([\d.]+)秒', line)
                if time_match:
                    current_data['transcription_time'] = float(time_match.group(1))
            elif '转录耗时:' in line:
                time_match = re.search(r'转录耗时:\s*([\d.]+)s', line)
                if time_match:
                    current_data['transcription_time'] = float(time_match.group(1))
        
        # 提取评估耗时（从"✅ 评估完成 (耗时: X.XX秒)"或"处理耗时: X.XXs"）
        if current_round:
            if '✅ 评估完成 (耗时:' in line:
                time_match = re.search(r'耗时:\s*([\d.]+)秒', line)
                if time_match:
                    current_data['evaluation_time'] = float(time_match.group(1))
            elif '处理耗时:' in line:
                time_match = re.search(r'处理耗时:\s*([\d.]+)s', line)
                if time_match:
                    current_data['evaluation_time'] = float(time_match.group(1))
    
    # 保存最后一轮数据（只有当有评估信息时才保存）
    if current_round is not None and current_data:
        # 只有当有评估分数或转录文本时才保存
        if current_data.get('score') is not None or current_data.get('transcribed_text'):
            result['conversations'].append(current_data.copy())
    
    # 提取最终用户画像
    user_profile_started = False
    user_profile = {}
    for i, line in enumerate(lines):
        if '步骤3: 最终用户画像' in line:
            user_profile_started = True
            continue
        elif user_profile_started:
            line_stripped = line.strip()
            if not line_stripped or '✅ 用户画像:' in line:
                continue
            elif '用户ID:' in line:
                user_profile['user_id'] = line.split('用户ID:')[1].strip()
            elif '综合分数:' in line and '📊' not in line:  # 避免提取对话中的分数
                score_match = re.search(r'(\d+\.?\d*)/100', line)
                if score_match:
                    user_profile['overall_score'] = float(score_match.group(1))
            elif 'CEFR等级:' in line and '🎯' not in line:  # 避免提取对话中的等级
                user_profile['cefr_level'] = line.split('CEFR等级:')[1].strip()
            elif '对话轮数:' in line:
                count_match = re.search(r'(\d+)', line)
                if count_match:
                    user_profile['conversation_count'] = int(count_match.group(1))
            elif '强项:' in line and '💪' not in line:  # 避免重复提取
                strengths_str = line.split('强项:')[1].strip()
                if strengths_str and strengths_str != '无':
                    user_profile['strengths'] = [s.strip() for s in strengths_str.split(',')]
            elif '弱项:' in line and '⚠️' not in line:  # 避免重复提取
                weaknesses_str = line.split('弱项:')[1].strip()
                if weaknesses_str and weaknesses_str != '无':
                    user_profile['weaknesses'] = [w.strip() for w in weaknesses_str.split(',')]
            elif '步骤4:' in line:
                # 在遇到步骤4之前，应该已经提取完用户画像
                break
            elif line_stripped and line_stripped.startswith('=') and len(line_stripped) > 50:
                # 遇到分隔线，继续处理（可能是步骤3和步骤4之间的分隔线）
                continue
    
    result['summary']['user_profile'] = user_profile if user_profile else {}
    
    # 提取性能统计
    stats_started = False
    stats = {}
    for i, line in enumerate(lines):
        if '步骤4: 测试总结' in line:
            stats_started = True
            continue
        elif stats_started:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            elif '✅ 成功完成' in line:
                continue
            elif '📊 性能统计:' in line:
                continue
            elif '总转录时间:' in line:
                time_match = re.search(r'(\d+\.?\d*)秒', line)
                if time_match:
                    stats['total_transcription_time'] = float(time_match.group(1))
            elif '平均转录时间:' in line:
                time_match = re.search(r'(\d+\.?\d*)秒', line)
                if time_match:
                    stats['avg_transcription_time'] = float(time_match.group(1))
            elif '总处理时间:' in line:
                time_match = re.search(r'(\d+\.?\d*)秒', line)
                if time_match:
                    stats['total_processing_time'] = float(time_match.group(1))
            elif '平均处理时间:' in line:
                time_match = re.search(r'(\d+\.?\d*)秒', line)
                if time_match:
                    stats['avg_processing_time'] = float(time_match.group(1))
            elif '📈 分数统计:' in line:
                continue
            elif '分数范围:' in line:
                range_match = re.search(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)', line)
                if range_match:
                    stats['score_range'] = (float(range_match.group(1)), float(range_match.group(2)))
            elif '平均分数:' in line:
                score_match = re.search(r'(\d+\.?\d*)', line)
                if score_match:
                    stats['avg_score'] = float(score_match.group(1))
            elif '最新分数:' in line:
                score_match = re.search(r'(\d+\.?\d*)', line)
                if score_match:
                    stats['latest_score'] = float(score_match.group(1))
            elif '📝 各轮详情:' in line:
                continue
            elif line_stripped and line_stripped.startswith('=') and len(line_stripped) > 50:
                # 遇到分隔线，检查是否是结束标志
                if i < len(lines) - 5:  # 如果不是最后几行，继续
                    continue
                else:
                    break
    
    result['summary']['statistics'] = stats
    
    return result

def format_summary(data: Dict) -> str:
    """格式化提取的数据为精简报告"""
    output = []
    
    # 标题
    output.append("=" * 80)
    output.append("FunASR 语音对话测试 - 精简报告")
    output.append("=" * 80)
    output.append("")
    
    # 配置信息
    if data['config']:
        output.append("📋 测试配置")
        output.append("-" * 80)
        if 'speech_provider' in data['config']:
            output.append(f"语音服务: {data['config']['speech_provider']}")
        if 'funasr_model' in data['config']:
            output.append(f"FunASR模型: {data['config']['funasr_model']}")
        if 'conversation_id' in data['config']:
            output.append(f"对话ID: {data['config']['conversation_id']}")
        output.append("")
    
    # 对话详情
    if data['conversations']:
        output.append("=" * 80)
        output.append("📝 对话详情")
        output.append("=" * 80)
        output.append("")
        
        for conv in data['conversations']:
            output.append(f"第 {conv['round']} 轮对话")
            if conv.get('test_scenario'):
                output.append(f"📋 测试场景: {conv['test_scenario']}")
            output.append("-" * 80)
            if conv['audio_file']:
                output.append(f"📤 音频文件: {conv['audio_file']}")
            else:
                output.append(f"📤 音频文件: (文本输入)")
            output.append(f"📝 用户输入（转录）: {conv['transcribed_text']}")
            if conv['score'] is not None:
                output.append(f"📊 评分: {conv['score']}/100")
            else:
                output.append(f"📊 评分: 未评估")
            output.append(f"🎯 CEFR等级: {conv['cefr_level'] if conv['cefr_level'] else '未评估'}")
            
            if conv['strengths']:
                output.append(f"💪 强项: {', '.join(conv['strengths'])}")
            else:
                output.append(f"💪 强项: 无")
            
            if conv['weaknesses']:
                output.append(f"⚠️  弱项: {', '.join(conv['weaknesses'])}")
            else:
                output.append(f"⚠️  弱项: 无")
            
            output.append(f"❓ 系统输出（下一题）: {conv['next_question']}")
            
            times = []
            if conv.get('transcription_time'):
                times.append(f"转录: {conv['transcription_time']:.2f}秒")
            if conv.get('evaluation_time'):
                times.append(f"评估: {conv['evaluation_time']:.2f}秒")
            if times:
                output.append(f"⏱️  耗时: {' | '.join(times)}")
            
            output.append("")
    
    # 最终用户画像
    if data['summary'].get('user_profile'):
        output.append("=" * 80)
        output.append("👤 最终用户画像")
        output.append("=" * 80)
        profile = data['summary']['user_profile']
        
        if 'user_id' in profile:
            output.append(f"用户ID: {profile['user_id']}")
        if 'overall_score' in profile:
            output.append(f"综合分数: {profile['overall_score']:.1f}/100")
        if 'cefr_level' in profile:
            output.append(f"CEFR等级: {profile['cefr_level']}")
        if 'conversation_count' in profile:
            output.append(f"对话轮数: {profile['conversation_count']}")
        if 'strengths' in profile and profile['strengths']:
            output.append(f"强项: {', '.join(profile['strengths'])}")
        if 'weaknesses' in profile and profile['weaknesses']:
            output.append(f"弱项: {', '.join(profile['weaknesses'])}")
        output.append("")
    
    # 性能统计
    if data['summary'].get('statistics'):
        output.append("=" * 80)
        output.append("📊 性能统计")
        output.append("=" * 80)
        stats = data['summary']['statistics']
        
        if 'total_transcription_time' in stats:
            output.append(f"总转录时间: {stats['total_transcription_time']:.2f}秒")
        if 'avg_transcription_time' in stats:
            output.append(f"平均转录时间: {stats['avg_transcription_time']:.2f}秒/轮")
        if 'total_processing_time' in stats:
            output.append(f"总处理时间: {stats['total_processing_time']:.2f}秒")
        if 'avg_processing_time' in stats:
            output.append(f"平均处理时间: {stats['avg_processing_time']:.2f}秒/轮")
        
        if 'score_range' in stats:
            output.append(f"分数范围: {stats['score_range'][0]:.1f} - {stats['score_range'][1]:.1f}")
        if 'avg_score' in stats:
            output.append(f"平均分数: {stats['avg_score']:.1f}")
        if 'latest_score' in stats:
            output.append(f"最新分数: {stats['latest_score']:.1f}")
        output.append("")
    
    output.append("=" * 80)
    output.append("报告生成完成")
    output.append("=" * 80)
    
    return '\n'.join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python extract_test_summary.py <日志文件路径> [输出文件路径]")
        print("示例: python extract_test_summary.py test_results_funasr_20251207_043625.txt summary.txt")
        sys.exit(1)
    
    log_file = sys.argv[1]
    
    if not os.path.exists(log_file):
        print(f"❌ 错误: 文件不存在: {log_file}")
        sys.exit(1)
    
    # 读取日志文件
    print(f"📖 正在读取日志文件: {log_file}")
    with open(log_file, 'r', encoding='utf-8') as f:
        log_content = f.read()
    
    # 提取数据
    print("🔍 正在提取关键信息...")
    data = extract_conversation_data(log_content)
    
    # 格式化输出
    print("📝 正在生成精简报告...")
    summary = format_summary(data)
    
    # 输出结果
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        print(f"✅ 精简报告已保存到: {output_file}")
    else:
        # 输出到控制台
        print("\n" + summary)
        print("\n💡 提示: 使用第二个参数可以保存到文件")
        print(f"   示例: python extract_test_summary.py {log_file} summary.txt")

if __name__ == "__main__":
    main()

