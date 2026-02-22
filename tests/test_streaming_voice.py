#!/usr/bin/env python3
"""
测试流式语音对话API的性能
"""
import asyncio
import websockets
import json
import base64
import time
import os
from pathlib import Path

async def test_streaming_voice():
    """测试流式语音对话"""
    
    # 1. 先创建对话
    import requests
    print("=" * 60)
    print("1. 创建对话")
    print("=" * 60)
    
    response = requests.post(
        "http://localhost:8000/conversations/start",
        json={"user_id": "test_performance_001"},
        timeout=10
    )
    
    if response.status_code != 200:
        print(f"❌ 创建对话失败: {response.status_code}")
        print(response.text)
        return
    
    data = response.json()
    conversation_id = data["conversation_id"]
    print(f"✓ 对话创建成功: {conversation_id}")
    print(f"  初始问题: {data.get('initial_question', '')[:100]}...")
    
    # 2. 读取测试音频文件
    print("\n" + "=" * 60)
    print("2. 准备测试音频")
    print("=" * 60)
    
    test_audio_dir = Path("test_audio")
    audio_files = list(test_audio_dir.glob("*.mp3"))
    
    if not audio_files:
        print("❌ 没有找到测试音频文件")
        return
    
    # 使用第一个音频文件
    audio_file = audio_files[0]
    print(f"✓ 使用测试音频: {audio_file.name}")
    print(f"  文件大小: {audio_file.stat().st_size / 1024:.2f} KB")
    
    # 读取音频文件
    with open(audio_file, 'rb') as f:
        audio_data = f.read()
    
    # 3. 连接WebSocket并测试
    print("\n" + "=" * 60)
    print("3. 连接WebSocket并发送音频")
    print("=" * 60)
    
    ws_url = f"ws://localhost:8000/streaming-voice/{conversation_id}/chat"
    
    timings = {
        "connect": 0,
        "send_start": 0,
        "send_audio": 0,
        "first_transcription": 0,
        "final_transcription": 0,
        "assessment": 0,
        "question": 0,
        "tts_start": 0,
        "tts_end": 0,
        "total": 0
    }
    
    start_time = time.time()
    
    try:
        async with websockets.connect(ws_url) as websocket:
            connect_time = time.time()
            timings["connect"] = connect_time - start_time
            print(f"✓ WebSocket连接成功 ({timings['connect']:.2f}s)")
            
            # 接收连接确认
            message = await websocket.recv()
            data = json.loads(message)
            print(f"  收到消息: {data.get('type')}")
            
            # 发送开始标记
            send_start_time = time.time()
            await websocket.send(json.dumps({"type": "start"}))
            timings["send_start"] = send_start_time - start_time
            
            # 接收录音开始确认
            message = await websocket.recv()
            data = json.loads(message)
            print(f"  {data.get('message')}")
            
            # 发送音频数据（分块发送）
            print("\n发送音频数据...")
            chunk_size = 8192  # 8KB chunks
            audio_sent_time = time.time()
            
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                await websocket.send(chunk)
                if i == 0:
                    print(f"  发送第一个块 ({len(chunk)} bytes)")
            
            timings["send_audio"] = time.time() - audio_sent_time
            print(f"✓ 音频发送完成 ({timings['send_audio']:.2f}s)")
            
            # 发送结束标记
            await websocket.send(json.dumps({"type": "audio_end"}))
            print("✓ 发送结束标记")
            
            # 接收处理结果
            print("\n等待处理结果...")
            first_transcription_time = None
            final_transcription_time = None
            
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    data = json.loads(message)
                    msg_type = data.get("type")
                    current_time = time.time() - start_time
                    
                    if msg_type == "transcription_partial":
                        if first_transcription_time is None:
                            first_transcription_time = current_time
                            timings["first_transcription"] = first_transcription_time
                            print(f"✓ 收到实时转录 ({current_time:.2f}s): {data.get('text', '')[:50]}...")
                    
                    elif msg_type == "transcription_final":
                        final_transcription_time = current_time
                        timings["final_transcription"] = final_transcription_time
                        print(f"✓ 收到最终转录 ({current_time:.2f}s): {data.get('text', '')[:100]}...")
                    
                    elif msg_type == "processing":
                        stage = data.get("stage", "unknown")
                        print(f"  [{stage}] {data.get('message', '')}")
                    
                    elif msg_type == "assessment":
                        timings["assessment"] = current_time
                        assessment = data.get("data", {}).get("assessment", {})
                        score = assessment.get("overall_score", 0)
                        cefr = assessment.get("cefr_level", "N/A")
                        print(f"✓ 收到评估结果 ({current_time:.2f}s): {score}分, CEFR {cefr}")
                    
                    elif msg_type == "question":
                        timings["question"] = current_time
                        question = data.get("text", "")
                        print(f"✓ 收到问题 ({current_time:.2f}s): {question[:100]}...")
                    
                    elif msg_type == "audio_chunk":
                        if timings["tts_start"] == 0:
                            timings["tts_start"] = current_time
                            print(f"✓ 开始接收TTS音频 ({current_time:.2f}s)")
                    
                    elif msg_type == "audio_end":
                        timings["tts_end"] = current_time
                        print(f"✓ TTS音频完成 ({current_time:.2f}s)")
                        break
                    
                    elif msg_type == "error":
                        print(f"❌ 错误: {data.get('message')}")
                        break
                
                except asyncio.TimeoutError:
                    print("❌ 超时：30秒内未收到完整响应")
                    break
            
            timings["total"] = time.time() - start_time
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. 性能分析
    print("\n" + "=" * 60)
    print("4. 性能分析")
    print("=" * 60)
    
    print(f"\n时间统计:")
    print(f"  连接时间:        {timings['connect']:.2f}s")
    print(f"  发送开始标记:    {timings['send_start']:.2f}s")
    print(f"  发送音频:        {timings['send_audio']:.2f}s")
    
    if timings['first_transcription']:
        print(f"  首次转录:        {timings['first_transcription']:.2f}s")
        print(f"  (首次转录延迟:   {timings['first_transcription'] - timings['send_audio']:.2f}s)")
    
    if timings['final_transcription']:
        print(f"  最终转录:        {timings['final_transcription']:.2f}s")
        print(f"  (转录耗时:       {timings['final_transcription'] - timings['send_audio']:.2f}s)")
    
    if timings['assessment']:
        print(f"  评估结果:        {timings['assessment']:.2f}s")
        print(f"  (评估耗时:       {timings['assessment'] - timings['final_transcription']:.2f}s)")
    
    if timings['question']:
        print(f"  问题生成:        {timings['question']:.2f}s")
        print(f"  (生成耗时:       {timings['question'] - timings['assessment']:.2f}s)")
    
    if timings['tts_start']:
        print(f"  TTS开始:         {timings['tts_start']:.2f}s")
        print(f"  (TTS延迟:        {timings['tts_start'] - timings['question']:.2f}s)")
    
    if timings['tts_end']:
        print(f"  TTS完成:         {timings['tts_end']:.2f}s")
        print(f"  (TTS耗时:        {timings['tts_end'] - timings['tts_start']:.2f}s)")
    
    print(f"\n  总耗时:          {timings['total']:.2f}s")
    
    # 性能建议
    print("\n性能分析:")
    if timings['total'] > 10:
        print("  ⚠️  总耗时超过10秒，需要优化")
    
    if timings['final_transcription'] and timings['final_transcription'] - timings['send_audio'] > 3:
        print("  ⚠️  转录耗时超过3秒，可能是STT服务较慢")
    
    if timings['assessment'] and timings['assessment'] - timings['final_transcription'] > 2:
        print("  ⚠️  评估耗时超过2秒，可能是LLM调用较慢")
    
    if timings['question'] and timings['question'] - timings['assessment'] > 2:
        print("  ⚠️  问题生成耗时超过2秒，可能是LLM调用较慢")
    
    if timings['tts_end'] and timings['tts_end'] - timings['tts_start'] > 3:
        print("  ⚠️  TTS耗时超过3秒，可能是TTS服务较慢")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(test_streaming_voice())



