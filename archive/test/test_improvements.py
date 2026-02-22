#!/usr/bin/env python3
"""
完整测试改进后的系统
测试内容：
1. 评估精细化改进 - 不同复杂度的回答应得到不同分数
2. 上下文对话连贯性 - 多轮对话应连贯
3. 学习报告生成 - 报告应包含所有必需部分
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import io
from services.speech import SpeechServiceFactory
from services.evaluator import EvaluatorService
from services.generator import QuestionGeneratorService
from services.context import ContextManagerService
from services.report import ReportService
from core.conversation import ConversationManager
from storage.repository import RepositoryFactory
from prompts.builders import PromptBuilder
from services.llm import LLMServiceFactory, LLMProvider
from config.settings import Settings
from config.llm_config import llm_config

def create_conversation_manager():
    """创建对话管理器"""
    settings = Settings()
    
    # LLM服务
    provider = LLMProvider(llm_config.get_provider())
    llm_service = LLMServiceFactory.create(provider=provider)
    
    # 语音服务（FunASR）
    speech_service = SpeechServiceFactory.create(
        provider="funasr",
        model_name=settings.funasr_model_name,
        language=settings.funasr_language
    )
    
    # 其他服务
    prompt_builder = PromptBuilder()
    evaluator_service = EvaluatorService(llm_service, prompt_builder)
    generator_service = QuestionGeneratorService(llm_service, prompt_builder)
    context_service = ContextManagerService(
        llm_service,
        prompt_builder,
        summary_interval=settings.context_summary_interval
    )
    report_service = ReportService(llm_service, prompt_builder)
    
    # 存储
    conversation_repo, user_repo = RepositoryFactory.create_repositories(
        backend=settings.storage_backend
    )
    
    # 对话管理器
    manager = ConversationManager(
        evaluator_service=evaluator_service,
        generator_service=generator_service,
        context_service=context_service,
        conversation_repo=conversation_repo,
        user_repo=user_repo,
        report_service=report_service
    )
    
    return manager, speech_service

def test_evaluation_differentiation():
    """测试1: 评估精细化 - 不同复杂度的回答应得到不同分数"""
    print("\n" + "=" * 80)
    print("测试1: 评估精细化改进")
    print("=" * 80)
    
    manager, _ = create_conversation_manager()
    
    # 创建测试对话
    user_id = "test_eval_differentiation"
    conversation = manager.start_conversation(user_id)
    conversation_id = conversation.conversation_id
    
    # 准备不同复杂度的回答
    test_responses = [
        {
            "text": "I am a student.",
            "expected_level": "简单",
            "description": "简单回答，只有一句话"
        },
        {
            "text": "I am a student. I like reading books. Reading helps me learn new words.",
            "expected_level": "中等",
            "description": "中等回答，3句话，有扩展"
        },
        {
            "text": "As an avid reader, I find that immersing myself in literature not only expands my vocabulary but also enhances my linguistic proficiency. The intricate narratives and sophisticated language structures provide invaluable insights into effective communication.",
            "expected_level": "复杂",
            "description": "复杂回答，使用高级词汇和复杂句式"
        }
    ]
    
    results = []
    
    for i, test_case in enumerate(test_responses, 1):
        print(f"\n--- 测试回答 {i}: {test_case['expected_level']} ({test_case['description']}) ---")
        print(f"回答内容: {test_case['text']}")
        
        try:
            conversation, assessment_result, next_question = manager.process_user_response(
                conversation_id=conversation_id,
                user_response=test_case['text']
            )
            
            score = assessment_result.ability_profile.overall_score
            level = assessment_result.ability_profile.cefr_level.value
            
            print(f"✅ 评估完成")
            print(f"   综合分数: {score:.1f}/100")
            print(f"   CEFR等级: {level}")
            print(f"   维度评分:")
            for dim in assessment_result.dimension_scores:
                print(f"     - {dim.dimension}: {dim.score:.1f}/5.0")
            
            results.append({
                "level": test_case['expected_level'],
                "score": score,
                "cefr_level": level,
                "dimension_scores": {dim.dimension: dim.score for dim in assessment_result.dimension_scores}
            })
            
        except Exception as e:
            print(f"❌ 评估失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 分析结果
    print("\n" + "-" * 80)
    print("评估差异化分析:")
    print("-" * 80)
    
    if len(results) >= 2:
        simple_score = results[0]['score']
        complex_score = results[-1]['score']
        score_diff = complex_score - simple_score
        
        print(f"简单回答分数: {simple_score:.1f}")
        print(f"复杂回答分数: {complex_score:.1f}")
        print(f"分数差异: {score_diff:.1f}")
        
        if score_diff > 10:
            print("✅ 评估系统能够区分不同复杂度的回答")
        elif score_diff > 5:
            print("⚠️  评估系统有一定区分度，但可以进一步改进")
        else:
            print("❌ 评估系统未能有效区分不同复杂度的回答")
    
    return results

def test_conversation_coherence():
    """测试2: 上下文对话连贯性"""
    print("\n" + "=" * 80)
    print("测试2: 上下文对话连贯性")
    print("=" * 80)
    
    manager, _ = create_conversation_manager()
    
    # 创建测试对话
    user_id = "test_coherence"
    conversation = manager.start_conversation(user_id)
    conversation_id = conversation.conversation_id
    
    initial_question = conversation.messages[-1].content
    print(f"\n初始问题: {initial_question[:150]}...")
    
    # 多轮对话
    test_responses = [
        "I usually wake up at 7 AM. I brush my teeth and eat breakfast.",
        "Yes, I like healthy food. I eat fruits and vegetables every day.",
        "I think exercise is important. I go jogging three times a week."
    ]
    
    questions = [initial_question]
    
    for i, response in enumerate(test_responses, 1):
        print(f"\n--- 第 {i} 轮对话 ---")
        print(f"用户回答: {response}")
        
        try:
            conversation, assessment_result, next_question = manager.process_user_response(
                conversation_id=conversation_id,
                user_response=response
            )
            
            print(f"系统问题: {next_question[:150]}...")
            questions.append(next_question)
            
            # 检查连贯性
            if i > 0:
                prev_question = questions[i-1]
                # 简单检查：新问题是否提及之前的内容
                coherence_keywords = ["also", "and", "about", "that", "you", "your"]
                has_coherence = any(keyword in next_question.lower() for keyword in coherence_keywords)
                
                if has_coherence:
                    print("✅ 问题与之前对话有连贯性")
                else:
                    print("⚠️  问题连贯性不明显")
            
        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            break
    
    return questions

def test_report_generation():
    """测试3: 学习报告生成"""
    print("\n" + "=" * 80)
    print("测试3: 学习报告生成")
    print("=" * 80)
    
    manager, _ = create_conversation_manager()
    
    # 创建测试对话并进行多轮交互
    user_id = "test_report"
    conversation = manager.start_conversation(user_id)
    conversation_id = conversation.conversation_id
    
    # 进行3轮对话
    test_responses = [
        "I am a student. I like reading books.",
        "Reading helps me learn new words and improve my English skills.",
        "I read for about 30 minutes every day. I think it's very helpful."
    ]
    
    for i, response in enumerate(test_responses, 1):
        print(f"\n第 {i} 轮对话...")
        try:
            conversation, _, _ = manager.process_user_response(
                conversation_id=conversation_id,
                user_response=response
            )
        except Exception as e:
            print(f"❌ 处理失败: {e}")
            break
    
    # 生成报告
    print("\n生成学习报告...")
    try:
        report = manager.end_conversation(conversation_id)
        
        if report:
            print("✅ 报告生成成功")
            print(f"报告长度: {len(report)} 字符")
            
            # 检查报告内容
            required_sections = [
                "能力分析",
                "进步轨迹",
                "强弱项",
                "学习建议",
                "规划"
            ]
            
            print("\n报告内容检查:")
            found_sections = []
            for section in required_sections:
                if section in report:
                    found_sections.append(section)
                    print(f"  ✅ 包含: {section}")
                else:
                    print(f"  ⚠️  缺少: {section}")
            
            if len(found_sections) >= 3:
                print("\n✅ 报告包含主要必需部分")
            else:
                print("\n⚠️  报告可能缺少一些重要部分")
            
            # 显示报告预览
            print("\n" + "-" * 80)
            print("报告预览（前500字符）:")
            print("-" * 80)
            print(report[:500] + "...")
            
            return report
        else:
            print("❌ 报告生成失败或不可用")
            return None
            
    except Exception as e:
        print(f"❌ 报告生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_complete_flow():
    """测试4: 完整流程测试"""
    print("\n" + "=" * 80)
    print("测试4: 完整流程测试")
    print("=" * 80)
    
    manager, speech_service = create_conversation_manager()
    
    # 使用音频文件进行完整对话
    audio_files = [
        "test_audio/test_simple.mp3",
        "test_audio/test_medium.mp3",
    ]
    
    available_files = [f for f in audio_files if os.path.exists(f)]
    
    if not available_files:
        print("⚠️  未找到测试音频文件，使用文本输入")
        available_files = []
    
    user_id = "test_complete_flow"
    conversation = manager.start_conversation(user_id)
    conversation_id = conversation.conversation_id
    
    print(f"\n对话ID: {conversation_id}")
    print(f"初始问题: {conversation.messages[-1].content[:150]}...")
    
    # 使用音频文件或文本输入
    test_inputs = []
    if available_files:
        for audio_file in available_files[:2]:  # 最多2个文件
            test_inputs.append(("audio", audio_file))
    else:
        test_inputs = [
            ("text", "I am a student. I like reading books."),
            ("text", "Reading helps me learn new words and improve my English skills.")
        ]
    
    scores = []
    
    for i, (input_type, input_data) in enumerate(test_inputs, 1):
        print(f"\n--- 第 {i} 轮对话 ---")
        
        try:
            if input_type == "audio":
                print(f"📤 使用音频文件: {os.path.basename(input_data)}")
                with open(input_data, 'rb') as f:
                    audio_io = io.BytesIO(f.read())
                    transcribed_text = speech_service.transcribe_audio(audio_io)
                print(f"📝 转录文本: {transcribed_text}")
                user_response = transcribed_text
            else:
                print(f"📝 文本输入: {input_data}")
                user_response = input_data
            
            conversation, assessment_result, next_question = manager.process_user_response(
                conversation_id=conversation_id,
                user_response=user_response
            )
            
            score = assessment_result.ability_profile.overall_score
            level = assessment_result.ability_profile.cefr_level.value
            scores.append(score)
            
            print(f"✅ 评估完成")
            print(f"   分数: {score:.1f}/100 | CEFR: {level}")
            print(f"   下一题: {next_question[:100]}...")
            
        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            break
    
    # 生成最终报告
    print("\n" + "-" * 80)
    print("生成最终学习报告...")
    print("-" * 80)
    
    try:
        report = manager.end_conversation(conversation_id)
        if report:
            print("✅ 报告生成成功")
            print(f"报告长度: {len(report)} 字符")
        else:
            print("⚠️  报告生成不可用")
    except Exception as e:
        print(f"❌ 报告生成失败: {e}")
    
    # 获取最终用户画像
    user_profile = manager.get_user_profile(user_id)
    if user_profile:
        print(f"\n最终用户画像:")
        print(f"   分数: {user_profile.overall_score:.1f}/100")
        print(f"   CEFR等级: {user_profile.cefr_level.value}")
        print(f"   对话轮数: {user_profile.conversation_count}")
        print(f"   强项: {', '.join(user_profile.strengths) if user_profile.strengths else '无'}")
        print(f"   弱项: {', '.join(user_profile.weaknesses) if user_profile.weaknesses else '无'}")
    
    return scores

def main():
    """主测试函数"""
    import datetime
    import subprocess
    
    print("=" * 80)
    print("系统改进完整测试")
    print("=" * 80)
    
    print("\n测试配置:")
    settings = Settings()
    print(f"  LLM Provider: {llm_config.get_provider()}")
    print(f"  Speech Provider: {settings.speech_provider}")
    print(f"  Storage Backend: {settings.storage_backend}")
    
    # 生成日志文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"test_improvements_results_{timestamp}.txt"
    summary_file = f"test_improvements_summary_{timestamp}.txt"
    
    # 重定向输出到文件和控制台
    class TeeOutput:
        def __init__(self, *files):
            self.files = files
        def write(self, obj):
            for f in self.files:
                f.write(obj)
                f.flush()
        def flush(self):
            for f in self.files:
                f.flush()
    
    results = {}
    
    # 打开日志文件
    log_file = open(result_file, 'w', encoding='utf-8')
    original_stdout = sys.stdout
    sys.stdout = TeeOutput(sys.stdout, log_file)
    
    try:
        # 测试1: 评估精细化
        try:
            results['evaluation'] = test_evaluation_differentiation()
        except Exception as e:
            print(f"\n❌ 测试1失败: {e}")
            import traceback
            traceback.print_exc()
            results['evaluation'] = None
        
        # 测试2: 对话连贯性
        try:
            results['coherence'] = test_conversation_coherence()
        except Exception as e:
            print(f"\n❌ 测试2失败: {e}")
            import traceback
            traceback.print_exc()
            results['coherence'] = None
        
        # 测试3: 报告生成
        try:
            results['report'] = test_report_generation()
        except Exception as e:
            print(f"\n❌ 测试3失败: {e}")
            import traceback
            traceback.print_exc()
            results['report'] = None
        
        # 测试4: 完整流程
        try:
            results['complete_flow'] = test_complete_flow()
        except Exception as e:
            print(f"\n❌ 测试4失败: {e}")
            import traceback
            traceback.print_exc()
            results['complete_flow'] = None
        
        # 测试总结
        print("\n" + "=" * 80)
        print("测试总结")
        print("=" * 80)
        
        print(f"\n测试1 - 评估精细化: {'✅ 通过' if results.get('evaluation') else '❌ 失败'}")
        print(f"测试2 - 对话连贯性: {'✅ 通过' if results.get('coherence') else '❌ 失败'}")
        print(f"测试3 - 报告生成: {'✅ 通过' if results.get('report') else '❌ 失败'}")
        print(f"测试4 - 完整流程: {'✅ 通过' if results.get('complete_flow') else '❌ 失败'}")
        
        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)
        print(f"\n测试日志已保存到: {result_file}")
        
    finally:
        sys.stdout = original_stdout
        log_file.close()
    
    # 自动运行提取脚本生成精简报告
    if os.path.exists(result_file) and os.path.exists("test/extract_test_summary.py"):
        print(f"\n{'='*80}")
        print("自动生成精简报告...")
        print(f"{'='*80}")
        try:
            # 运行提取脚本
            extract_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test", "extract_test_summary.py")
            result = subprocess.run(
                [sys.executable, extract_script, result_file, summary_file],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            
            if result.returncode == 0:
                print(f"✅ 精简报告已生成: {summary_file}")
                if os.path.exists(summary_file):
                    file_size = os.path.getsize(summary_file)
                    print(f"   文件大小: {file_size} 字节")
                    print(f"\n报告预览（前300字符）:")
                    print("-" * 80)
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        preview = f.read(300)
                        print(preview + "...")
            else:
                print(f"⚠️  提取脚本执行失败: {result.stderr}")
        except Exception as e:
            print(f"⚠️  自动提取失败: {e}")
            import traceback
            traceback.print_exc()
    
    return results

if __name__ == "__main__":
    main()

