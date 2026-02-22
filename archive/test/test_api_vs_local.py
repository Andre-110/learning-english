#!/usr/bin/env python3
"""
对比测试：Whisper API vs FunASR本地模型
"""
import time
import io
from pathlib import Path
from services.speech import SpeechServiceFactory
from config.settings import Settings

def test_whisper_api():
    """测试Whisper API性能"""
    print("=" * 60)
    print("测试 Whisper API")
    print("=" * 60)
    
    try:
        speech_service = SpeechServiceFactory.create(provider="whisper")
        print("✓ Whisper API服务初始化成功")
        
        # 读取测试音频
        test_audio_dir = Path("test_audio")
        audio_files = list(test_audio_dir.glob("*.mp3"))
        
        if not audio_files:
            print("❌ 没有找到测试音频文件")
            return None
        
        results = []
        for audio_file in sorted(audio_files):
            print(f"\n测试文件: {audio_file.name}")
            print(f"  文件大小: {audio_file.stat().st_size / 1024:.2f} KB")
            
            with open(audio_file, 'rb') as f:
                audio_data = f.read()
            
            audio_file_obj = io.BytesIO(audio_data)
            
            start_time = time.time()
            try:
                transcribed_text = speech_service.transcribe_audio(audio_file_obj)
                elapsed_time = time.time() - start_time
                
                print(f"  ✓ 转录成功")
                print(f"  耗时: {elapsed_time:.2f}s")
                print(f"  转录文本: {transcribed_text[:100]}...")
                
                results.append({
                    "file": audio_file.name,
                    "size_kb": audio_file.stat().st_size / 1024,
                    "time": elapsed_time
                })
            except Exception as e:
                print(f"  ❌ 转录失败: {e}")
                return None
        
        return results
        
    except Exception as e:
        print(f"❌ Whisper API测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_funasr_local():
    """测试FunASR本地模型性能"""
    print("\n" + "=" * 60)
    print("测试 FunASR 本地模型")
    print("=" * 60)
    
    try:
        settings = Settings()
        speech_service = SpeechServiceFactory.create(
            provider="funasr",
            model_dir=settings.funasr_model_dir,
            model_name=settings.funasr_model_name,
            language=settings.funasr_language
        )
        print("✓ FunASR服务初始化成功")
        
        # 读取测试音频
        test_audio_dir = Path("test_audio")
        audio_files = list(test_audio_dir.glob("*.mp3"))
        
        if not audio_files:
            print("❌ 没有找到测试音频文件")
            return None
        
        results = []
        first_load_time = None
        
        for i, audio_file in enumerate(sorted(audio_files)):
            print(f"\n测试文件: {audio_file.name}")
            print(f"  文件大小: {audio_file.stat().st_size / 1024:.2f} KB")
            
            with open(audio_file, 'rb') as f:
                audio_data = f.read()
            
            audio_file_obj = io.BytesIO(audio_data)
            
            start_time = time.time()
            try:
                transcribed_text = speech_service.transcribe_audio(audio_file_obj)
                elapsed_time = time.time() - start_time
                
                if i == 0:
                    first_load_time = elapsed_time
                    print(f"  ✓ 转录成功（首次加载）")
                else:
                    print(f"  ✓ 转录成功")
                
                print(f"  耗时: {elapsed_time:.2f}s")
                print(f"  转录文本: {transcribed_text[:100]}...")
                
                results.append({
                    "file": audio_file.name,
                    "size_kb": audio_file.stat().st_size / 1024,
                    "time": elapsed_time,
                    "is_first": i == 0
                })
            except Exception as e:
                print(f"  ❌ 转录失败: {e}")
                return None
        
        return results, first_load_time
        
    except Exception as e:
        print(f"❌ FunASR测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def compare_results(api_results, local_results, first_load_time):
    """对比结果"""
    print("\n" + "=" * 60)
    print("性能对比")
    print("=" * 60)
    
    if not api_results or not local_results:
        print("❌ 无法对比：缺少测试结果")
        return
    
    # 排除首次加载的时间
    local_times = [r["time"] for r in local_results if not r.get("is_first", False)]
    api_times = [r["time"] for r in api_results]
    
    avg_api = sum(api_times) / len(api_times) if api_times else 0
    avg_local = sum(local_times) / len(local_times) if local_times else 0
    
    print(f"\n平均转录时间:")
    print(f"  Whisper API:    {avg_api:.2f}s")
    print(f"  FunASR本地:     {avg_local:.2f}s (排除首次加载)")
    print(f"  FunASR首次加载: {first_load_time:.2f}s")
    
    if avg_api > 0 and avg_local > 0:
        speedup = avg_local / avg_api if avg_api > 0 else 0
        if speedup > 1:
            print(f"\n  ✅ Whisper API 快 {speedup:.2f}x")
        else:
            print(f"\n  ✅ FunASR本地 快 {1/speedup:.2f}x")
    
    print(f"\n详细对比:")
    print(f"{'文件':<20} | {'API时间':<10} | {'本地时间':<10} | {'差异':<10}")
    print("-" * 60)
    
    for i, api_r in enumerate(api_results):
        if i < len(local_results):
            local_r = local_results[i]
            diff = local_r["time"] - api_r["time"]
            diff_pct = (diff / api_r["time"] * 100) if api_r["time"] > 0 else 0
            
            print(f"{api_r['file']:<20} | {api_r['time']:>8.2f}s | {local_r['time']:>8.2f}s | {diff:>+8.2f}s ({diff_pct:>+6.1f}%)")
    
    # 建议
    print(f"\n建议:")
    if avg_api < avg_local:
        print(f"  ✅ 推荐使用 Whisper API")
        print(f"     - 速度更快（快 {avg_local/avg_api:.2f}x）")
        print(f"     - 无需本地模型加载")
        print(f"     - 无需GPU资源")
    else:
        print(f"  ✅ 推荐使用 FunASR本地模型")
        print(f"     - 速度更快（快 {avg_api/avg_local:.2f}x）")
        print(f"     - 无需网络连接")
        print(f"     - 数据隐私更好")
        print(f"     - 注意：首次加载需要{first_load_time:.1f}秒")

def main():
    """主函数"""
    print("=" * 60)
    print("API vs 本地模型性能对比测试")
    print("=" * 60)
    
    # 测试Whisper API
    api_results = test_whisper_api()
    
    # 测试FunASR本地
    local_results, first_load_time = test_funasr_local()
    
    # 对比结果
    if api_results and local_results:
        compare_results(api_results, local_results, first_load_time)
    else:
        print("\n⚠️  部分测试失败，无法完整对比")

if __name__ == "__main__":
    main()



