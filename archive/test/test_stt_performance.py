#!/usr/bin/env python3
"""
测试STT性能（不依赖数据库）
"""
import time
import io
from pathlib import Path
from services.speech import SpeechServiceFactory
from config.settings import Settings

def test_stt_performance():
    """测试STT转录性能"""
    print("=" * 60)
    print("STT性能测试")
    print("=" * 60)
    
    # 1. 初始化STT服务
    print("\n1. 初始化STT服务...")
    settings = Settings()
    
    if settings.speech_provider == "funasr":
        speech_service = SpeechServiceFactory.create(
            provider="funasr",
            model_dir=settings.funasr_model_dir,
            model_name=settings.funasr_model_name,
            language=settings.funasr_language
        )
    else:
        speech_service = SpeechServiceFactory.create(provider="whisper")
    
    print(f"✓ STT服务: {settings.speech_provider}")
    
    # 2. 读取测试音频
    print("\n2. 准备测试音频...")
    test_audio_dir = Path("test_audio")
    audio_files = list(test_audio_dir.glob("*.mp3"))
    
    if not audio_files:
        print("❌ 没有找到测试音频文件")
        return
    
    # 测试所有音频文件
    results = []
    for audio_file in sorted(audio_files):
        print(f"\n测试文件: {audio_file.name}")
        print(f"  文件大小: {audio_file.stat().st_size / 1024:.2f} KB")
        
        # 读取音频
        with open(audio_file, 'rb') as f:
            audio_data = f.read()
        
        # 测试转录
        audio_file_obj = io.BytesIO(audio_data)
        
        start_time = time.time()
        try:
            transcribed_text = speech_service.transcribe_audio(audio_file_obj)
            elapsed_time = time.time() - start_time
            
            print(f"  ✓ 转录成功")
            print(f"  耗时: {elapsed_time:.2f}s")
            print(f"  转录文本: {transcribed_text[:100]}...")
            print(f"  文本长度: {len(transcribed_text)} 字符")
            
            # 计算速度
            audio_duration = len(audio_data) / 1024 / 128  # 假设128kbps
            speed_ratio = audio_duration / elapsed_time if elapsed_time > 0 else 0
            
            results.append({
                "file": audio_file.name,
                "size_kb": audio_file.stat().st_size / 1024,
                "time": elapsed_time,
                "text_length": len(transcribed_text),
                "speed_ratio": speed_ratio
            })
            
        except Exception as e:
            print(f"  ❌ 转录失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 3. 性能总结
    if results:
        print("\n" + "=" * 60)
        print("3. 性能总结")
        print("=" * 60)
        
        avg_time = sum(r["time"] for r in results) / len(results)
        avg_size = sum(r["size_kb"] for r in results) / len(results)
        avg_speed = sum(r["speed_ratio"] for r in results) / len(results)
        
        print(f"\n平均性能:")
        print(f"  平均文件大小: {avg_size:.2f} KB")
        print(f"  平均转录时间: {avg_time:.2f}s")
        print(f"  平均速度比: {avg_speed:.2f}x")
        
        print(f"\n详细结果:")
        for r in results:
            print(f"  {r['file']:20s} | {r['size_kb']:6.2f} KB | {r['time']:5.2f}s | {r['speed_ratio']:4.2f}x")
        
        # 性能评估
        print(f"\n性能评估:")
        if avg_time < 2:
            print("  ✓ 转录速度很快 (< 2s)")
        elif avg_time < 5:
            print("  ⚠️  转录速度一般 (2-5s)")
        else:
            print("  ❌ 转录速度较慢 (> 5s)")
            print("  建议:")
            print("    - 检查网络连接（如果使用API）")
            print("    - 考虑使用本地STT服务（FunASR）")
            print("    - 优化音频格式和大小")

if __name__ == "__main__":
    test_stt_performance()



