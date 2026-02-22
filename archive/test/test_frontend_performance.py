#!/usr/bin/env python3
"""
测试前端性能测试功能
模拟完整的语音对话流程并测量性能
"""
import asyncio
import websockets
import json
import base64
import time
import requests
from pathlib import Path

async def test_frontend_performance():
    """测试前端性能测试功能"""
    
    print("=" * 60)
    print("前端性能测试功能验证")
    print("=" * 60)
    
    # 1. 创建对话
    print("\n1. 创建对话...")
    try:
        response = requests.post(
            "http://localhost:8000/conversations/start",
            json={"user_id": "perf_test_user"},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ 创建对话失败: {response.status_code}")
            print(response.text)
            return
        
        data = response.json()
        conversation_id = data["conversation_id"]
        print(f"✓ 对话创建成功: {conversation_id}")
    except Exception as e:
        print(f"❌ 创建对话失败: {e}")
        return
    
    # 2. 读取测试音频
    print("\n2. 准备测试音频...")
    test_audio_dir = Path("test_audio")
    audio_files = list(test_audio_dir.glob("*.mp3"))
    
    if not audio_files:
        print("❌ 没有找到测试音频文件")
        return
    
    audio_file = audio_files[0]  # 使用第一个音频文件
    print(f"✓ 使用测试音频: {audio_file.name}")
    
    with open(audio_file, 'rb') as f:
        audio_data = f.read()
    
    print(f"  文件大小: {len(audio_data) / 1024:.2f} KB")
    
    # 3. 连接WebSocket并测试
    print("\n3. 连接WebSocket并测试性能...")
    ws_url = f"ws://localhost:8000/streaming-voice/{conversation_id}/chat"
    
    timings = {}
    start_time = time.time()
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✓ WebSocket连接成功")
            
            # 接收连接确认
            message = await websocket.recv()
            data = json.loads(message)
            print(f"  收到: {data.get('type')}")
            
            # 发送开始标记
            await websocket.send(json.dumps({"type": "start"}))
            timings["start_sent"] = time.time()
            
            # 接收录音开始确认
            message = await websocket.recv()
            data = json.loads(message)
            print(f"  {data.get('message')}")
            
            # 模拟录音（发送音频数据）
            print("\n4. 发送音频数据...")
            chunk_size = 8192
            audio_sent_time = time.time()
            
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                await websocket.send(chunk)
            
            timings["audio_sent"] = time.time()
            print(f"✓ 音频发送完成 ({timings['audio_sent'] - audio_sent_time:.2f}s)")
            
            # 发送结束标记
            await websocket.send(json.dumps({"type": "audio_end"}))
            print("✓ 发送结束标记")
            
            # 接收处理结果并记录时间
            print("\n5. 等待处理结果...")
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    data = json.loads(message)
                    msg_type = data.get("type")
                    current_time = time.time()
                    
                    if msg_type == "transcription_partial":
                        if "first_transcription" not in timings:
                            timings["first_transcription"] = current_time
                            print(f"✓ 收到实时转录 ({current_time - timings['audio_sent']:.2f}s)")
                    
                    elif msg_type == "transcription_final":
                        timings["final_transcription"] = current_time
                        print(f"✓ 收到最终转录 ({current_time - timings['audio_sent']:.2f}s): {data.get('text', '')[:50]}...")
                    
                    elif msg_type == "assessment":
                        timings["assessment"] = current_time
                        assessment = data.get("data", {}).get("assessment", {})
                        print(f"✓ 收到评估 ({current_time - timings['audio_sent']:.2f}s): {assessment.get('overall_score', 0)}分")
                    
                    elif msg_type == "question":
                        timings["question"] = current_time
                        print(f"✓ 收到问题 ({current_time - timings['audio_sent']:.2f}s): {data.get('text', '')[:50]}...")
                    
                    elif msg_type == "audio_chunk":
                        if "tts_start" not in timings:
                            timings["tts_start"] = current_time
                            print(f"✓ 开始接收TTS音频 ({current_time - timings['audio_sent']:.2f}s)")
                    
                    elif msg_type == "audio_end":
                        timings["tts_end"] = current_time
                        print(f"✓ TTS完成 ({current_time - timings['audio_sent']:.2f}s)")
                        break
                    
                    elif msg_type == "error":
                        print(f"❌ 错误: {data.get('message')}")
                        break
                
                except asyncio.TimeoutError:
                    print("❌ 超时：30秒内未收到完整响应")
                    break
            
            total_time = time.time() - start_time
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 6. 性能分析
    print("\n" + "=" * 60)
    print("6. 性能分析")
    print("=" * 60)
    
    if timings.get("audio_sent"):
        print(f"\n时间统计（从音频发送开始）:")
        
        if timings.get("first_transcription"):
            t = timings["first_transcription"] - timings["audio_sent"]
            print(f"  首次转录: {t:.2f}s")
        
        if timings.get("final_transcription"):
            t = timings["final_transcription"] - timings["audio_sent"]
            print(f"  最终转录: {t:.2f}s")
        
        if timings.get("assessment"):
            t = timings["assessment"] - timings.get("final_transcription", timings["audio_sent"])
            print(f"  评估处理: {t:.2f}s")
        
        if timings.get("question"):
            t = timings["question"] - timings.get("assessment", timings["audio_sent"])
            print(f"  问题生成: {t:.2f}s")
        
        if timings.get("tts_start") and timings.get("tts_end"):
            t = timings["tts_end"] - timings["tts_start"]
            print(f"  TTS生成: {t:.2f}s")
        
        if timings.get("tts_end"):
            total_process = timings["tts_end"] - timings["audio_sent"]
            print(f"\n  总处理时间: {total_process:.2f}s")
            
            # 性能评估
            if total_process < 5:
                print("  ✅ 性能优秀！")
            elif total_process < 10:
                print("  ⚠️  性能良好")
            else:
                print("  ❌ 性能较慢")
    
    print(f"\n总耗时: {total_time:.2f}s")
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n提示：现在可以在前端页面使用性能测试功能")
    print("1. 打开浏览器访问 http://localhost:8000/")
    print("2. 点击'开始性能测试'按钮")
    print("3. 进行录音，查看实时性能数据")

if __name__ == "__main__":
    asyncio.run(test_frontend_performance())


