#!/usr/bin/env python3
"""
测试豆包 ASR 服务
"""
import asyncio
import sys
import logging
sys.path.insert(0, '/home/ubuntu/learning_english')

# 启用 DEBUG 日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')

from dotenv import load_dotenv
load_dotenv()

from services.doubao_asr import DoubaoASR, DoubaoASRConfig

async def test_doubao_asr():
    print("=" * 50)
    print("豆包 ASR 测试")
    print("=" * 50)
    
    # 读取测试音频
    audio_path = "/home/ubuntu/learning_english/archive/test_audio.wav"
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    
    print(f"测试音频: {audio_path}")
    print(f"音频大小: {len(audio_data)} bytes")
    
    # 跳过 WAV 头（44 bytes）
    pcm_data = audio_data[44:]
    print(f"PCM 数据大小: {len(pcm_data)} bytes")
    
    # 创建 ASR 实例
    config = DoubaoASRConfig(language="en")
    asr = DoubaoASR(config)
    
    # 回调函数
    transcripts = []
    
    async def on_transcript(text: str, is_final: bool):
        tag = "[Final]" if is_final else "[Interim]"
        print(f"  {tag} {text}")
        if is_final:
            transcripts.append(text)
    
    async def on_error(e: Exception):
        print(f"  [Error] {e}")
    
    # 开始流式连接
    print("\n开始流式连接...")
    success = await asr.start_stream(
        on_transcript=on_transcript,
        on_error=on_error
    )
    
    if not success:
        print("连接失败！")
        return
    
    print("连接成功，开始发送音频...")
    
    # 分块发送音频（模拟实时流）
    chunk_size = 1024
    sent_count = 0
    for i in range(0, len(pcm_data), chunk_size):
        chunk = pcm_data[i:i + chunk_size]
        await asr.send_audio(chunk)
        sent_count += 1
        if sent_count % 10 == 0:
            print(f"  已发送 {sent_count} 块...")
        await asyncio.sleep(0.03)  # 模拟实时发送
    
    print(f"音频发送完成，共 {sent_count} 块")
    
    # 停止流式连接
    print("\n停止流式连接...")
    result = await asr.stop_stream()
    
    print("\n" + "=" * 50)
    print("测试结果")
    print("=" * 50)
    print(f"最终转录: {result}")
    print(f"收到的转录数: {len(transcripts)}")
    
    if result:
        print("\n✅ 豆包 ASR 测试成功！")
    else:
        print("\n❌ 豆包 ASR 测试失败 - 无转录结果")

if __name__ == "__main__":
    asyncio.run(test_doubao_asr())
