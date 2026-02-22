#!/usr/bin/env python3
"""
使用FunASR本地部署完成完整的英语学习对话流程测试
直接调用服务层，不依赖API服务
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
from core.conversation import ConversationManager
from storage.repository import RepositoryFactory
from prompts.builders import PromptBuilder
from services.llm import LLMServiceFactory, LLMProvider
from config.settings import Settings
from config.llm_config import llm_config

def create_conversation_manager():
    """创建对话管理器（使用FunASR）"""
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
        user_repo=user_repo
    )
    
    return manager, speech_service

def test_complete_conversation_flow():
    """测试完整的对话流程"""
    print("=" * 70)
    print("FunASR本地部署 - 完整对话流程测试")
    print("=" * 70)
    
    # 获取音频文件
    audio_files = [
        "test_audio/test_simple.mp3",
        "test_audio/test_medium.mp3",
        "test_audio/test_mixed.mp3",
        "test_audio/test_advanced.mp3",
    ]
    
    available_files = [f for f in audio_files if os.path.exists(f)]
    
    if not available_files:
        print("❌ 未找到测试音频文件")
        return False
    
    print(f"\n📁 找到 {len(available_files)} 个测试音频文件:")
    for i, f in enumerate(available_files, 1):
        size = os.path.getsize(f) / 1024
        print(f"   {i}. {os.path.basename(f)} ({size:.1f} KB)")
    
    # 创建服务
    print("\n" + "=" * 70)
    print("初始化服务（FunASR本地部署）")
    print("=" * 70)
    
    try:
        manager, speech_service = create_conversation_manager()
        print("✅ 服务初始化成功")
        print(f"   语音服务: {type(speech_service).__name__}")
    except Exception as e:
        print(f"❌ 服务初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 步骤1: 开始对话
    print("\n" + "=" * 70)
    print("步骤1: 开始对话")
    print("=" * 70)
    
    user_id = "test_user_funasr_complete"
    
    try:
        conversation = manager.start_conversation(user_id)
        conversation_id = conversation.conversation_id
        initial_question = conversation.messages[-1].content if conversation.messages else ""
        
        print(f"✅ 对话已开始")
        print(f"   对话ID: {conversation_id}")
        print(f"   初始问题: {initial_question[:150]}...")
    except Exception as e:
        print(f"❌ 开始对话失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 步骤2: 使用音频文件进行多轮对话
    print("\n" + "=" * 70)
    print("步骤2: 使用FunASR转录音频并进行多轮对话")
    print("=" * 70)
    
    conversation_results = []
    test_rounds = min(len(available_files), 4)  # 使用所有4个音频文件
    
    for round_num in range(1, test_rounds + 1):
        audio_file = available_files[round_num - 1]
        print(f"\n{'='*70}")
        print(f"第 {round_num} 轮对话")
        print(f"{'='*70}")
        print(f"📤 音频文件: {os.path.basename(audio_file)}")
        
        try:
            # 1. 使用FunASR转录音频
            print("   ⏳ 步骤1: FunASR转录音频...")
            import time
            start_time = time.time()
            
            with open(audio_file, 'rb') as f:
                audio_io = io.BytesIO(f.read())
                transcribed_text = speech_service.transcribe_audio(audio_io)
            
            transcription_time = time.time() - start_time
            print(f"   ✅ 转录成功 (耗时: {transcription_time:.2f}秒)")
            print(f"   📝 转录文本: {transcribed_text}")
            
            if not transcribed_text or not transcribed_text.strip():
                print("   ⚠️  转录结果为空，跳过此轮")
                continue
            
            # 2. 处理用户回答
            print("   ⏳ 步骤2: 评估用户回答...")
            start_time = time.time()
            
            conversation, assessment_result, next_question = manager.process_user_response(
                conversation_id=conversation_id,
                user_response=transcribed_text.strip()
            )
            
            processing_time = time.time() - start_time
            
            # 3. 显示结果
            ability_profile = assessment_result.ability_profile
            print(f"   ✅ 评估完成 (耗时: {processing_time:.2f}秒)")
            print(f"   📊 综合分数: {ability_profile.overall_score:.1f}/100")
            print(f"   🎯 CEFR等级: {ability_profile.cefr_level.value}")
            print(f"   💪 强项: {', '.join(ability_profile.strengths) if ability_profile.strengths else '无'}")
            print(f"   ⚠️  弱项: {', '.join(ability_profile.weaknesses) if ability_profile.weaknesses else '无'}")
            print(f"   ❓ 下一题: {next_question[:100]}...")
            
            conversation_results.append({
                'round': round_num,
                'file': os.path.basename(audio_file),
                'transcribed': transcribed_text,
                'score': ability_profile.overall_score,
                'level': ability_profile.cefr_level.value,
                'transcription_time': transcription_time,
                'processing_time': processing_time,
                'next_question': next_question
            })
            
            # 短暂延迟
            import time
            time.sleep(0.5)
            
        except Exception as e:
            print(f"   ❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            break
    
    # 步骤3: 获取最终用户画像
    print("\n" + "=" * 70)
    print("步骤3: 最终用户画像")
    print("=" * 70)
    
    try:
        user_profile = manager.get_user_profile(user_id)
        if user_profile:
            print(f"✅ 用户画像:")
            print(f"   用户ID: {user_profile.user_id}")
            print(f"   综合分数: {user_profile.overall_score:.1f}/100")
            print(f"   CEFR等级: {user_profile.cefr_level.value}")
            print(f"   对话轮数: {user_profile.conversation_count}")
            print(f"   强项: {', '.join(user_profile.strengths) if user_profile.strengths else '无'}")
            print(f"   弱项: {', '.join(user_profile.weaknesses) if user_profile.weaknesses else '无'}")
    except Exception as e:
        print(f"⚠️  获取用户画像失败: {e}")
    
    # 步骤4: 测试总结
    print("\n" + "=" * 70)
    print("步骤4: 测试总结")
    print("=" * 70)
    
    if conversation_results:
        print(f"\n✅ 成功完成 {len(conversation_results)} 轮对话")
        
        total_transcription_time = sum(r['transcription_time'] for r in conversation_results)
        total_processing_time = sum(r['processing_time'] for r in conversation_results)
        scores = [r['score'] for r in conversation_results]
        
        print(f"\n📊 性能统计:")
        print(f"   总转录时间: {total_transcription_time:.2f}秒")
        print(f"   平均转录时间: {total_transcription_time/len(conversation_results):.2f}秒/轮")
        print(f"   总处理时间: {total_processing_time:.2f}秒")
        print(f"   平均处理时间: {total_processing_time/len(conversation_results):.2f}秒/轮")
        
        if scores:
            print(f"\n📈 分数统计:")
            print(f"   分数范围: {min(scores):.1f} - {max(scores):.1f}")
            print(f"   平均分数: {sum(scores)/len(scores):.1f}")
            print(f"   最新分数: {scores[-1]:.1f}")
        
        print(f"\n📝 各轮详情:")
        for r in conversation_results:
            print(f"\n   第{r['round']}轮: {os.path.basename(r['file'])}")
            print(f"     转录: {r['transcribed'][:60]}...")
            print(f"     分数: {r['score']:.1f} | CEFR: {r['level']}")
            print(f"     转录耗时: {r['transcription_time']:.2f}s | 处理耗时: {r['processing_time']:.2f}s")
    else:
        print("\n⚠️  未完成任何对话轮次")
    
    print("\n" + "=" * 70)
    print("✅ FunASR本地部署完整对话流程测试完成！")
    print("=" * 70)
    
    return len(conversation_results) > 0

def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("FunASR本地部署 - 完整对话流程测试")
    print("=" * 70)
    
    # 检查配置
    settings = Settings()
    print(f"\n📋 当前配置:")
    print(f"   SPEECH_PROVIDER: {settings.speech_provider}")
    print(f"   FUNASR_MODEL_NAME: {settings.funasr_model_name}")
    print(f"   FUNASR_LANGUAGE: {settings.funasr_language}")
    
    if settings.speech_provider != "funasr":
        print(f"\n⚠️  警告: SPEECH_PROVIDER 不是 'funasr'")
        print("   将强制使用FunASR进行测试")
    
    success = test_complete_conversation_flow()
    return success

if __name__ == "__main__":
    import datetime
    import subprocess
    
    # 自动保存结果到文件
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"test_results_funasr_{timestamp}.txt"
    summary_file = f"test_summary_funasr_{timestamp}.txt"
    
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
    
    with open(result_file, 'w', encoding='utf-8') as f:
        original_stdout = sys.stdout
        sys.stdout = TeeOutput(sys.stdout, f)
        try:
            success = main()
            print(f"\n\n{'='*70}")
            print(f"测试结果已保存到: {result_file}")
            print(f"{'='*70}")
        finally:
            sys.stdout = original_stdout
    
    # 自动运行提取脚本生成精简报告
    if os.path.exists(result_file) and os.path.exists("test/extract_test_summary.py"):
        print(f"\n{'='*70}")
        print("自动生成精简报告...")
        print(f"{'='*70}")
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
            else:
                print(f"⚠️  提取脚本执行失败: {result.stderr}")
        except Exception as e:
            print(f"⚠️  自动提取失败: {e}")
    
    sys.exit(0 if success else 1)

