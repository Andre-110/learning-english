#!/usr/bin/env python3
"""
WebSocket 完整端到端测试 - 使用真实录音

测试完整流程：
1. 连接 WebSocket
2. 发送 start 信号
3. 发送真实语音音频
4. 发送 audio_end 信号
5. 接收转录、评估、AI 回复、TTS 音频
"""

import asyncio
import json
import wave
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


async def test_full_flow():
    """完整流程测试"""
    import websockets
    
    print("\n" + "=" * 60)
    print("  WebSocket 完整端到端测试")
    print("=" * 60)
    
    # 检查测试音频
    audio_file = "/tmp/test_speech_16k.wav"
    if not os.path.exists(audio_file):
        print(f"❌ 测试音频不存在: {audio_file}")
        return False
    
    # 读取音频
    with wave.open(audio_file, 'rb') as f:
        sample_rate = f.getframerate()
        channels = f.getnchannels()
        pcm_data = f.readframes(f.getnframes())
    
    print(f"✓ 测试音频: {len(pcm_data)} bytes, {sample_rate}Hz, {channels} channels")
    
    # 连接 WebSocket
    ws_url = "ws://localhost:8000/ws/openrouter-audio?user_id=test_full_flow"
    print(f"\n连接: {ws_url}")
    
    received_messages = []
    
    try:
        async with websockets.connect(ws_url, ping_interval=None, close_timeout=10) as ws:
            # 接收初始消息
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            print(f"[1] 收到: {data.get('type')} - initial_question: {data.get('initial_question', '(无)')[:50]}...")
            received_messages.append(data)
            
            # 发送 start 信号
            print("\n[2] 发送: start")
            await ws.send(json.dumps({"type": "start"}))
            
            # 发送音频数据 - 模拟前端录音（每块带 WAV 头）
            print("[3] 发送音频...")
            
            import io
            
            # 模拟前端：每 100ms 发送一个 WAV 块（带头）
            chunk_duration_ms = 100
            samples_per_chunk = int(sample_rate * chunk_duration_ms / 1000)
            bytes_per_chunk = samples_per_chunk * 2  # 16-bit = 2 bytes
            
            chunks_sent = 0
            for i in range(0, len(pcm_data), bytes_per_chunk):
                chunk_pcm = pcm_data[i:i+bytes_per_chunk]
                
                # 为每个块创建完整的 WAV 格式
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, 'wb') as wav_file:
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(chunk_pcm)
                
                wav_chunk = wav_buffer.getvalue()
                await ws.send(wav_chunk)
                chunks_sent += 1
                
                # 模拟真实录音间隔
                await asyncio.sleep(chunk_duration_ms / 1000)
            
            print(f"    发送了 {chunks_sent} 块音频 (每块 {chunk_duration_ms}ms)")
            
            # 发送 audio_end 信号
            print("[4] 发送: audio_end")
            await ws.send(json.dumps({"type": "audio_end"}))
            
            # 接收响应
            print("\n[5] 等待响应...")
            
            transcription = None
            evaluation = None
            response = None
            audio_chunks = 0
            
            timeout = 60  # 60秒超时
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    
                    if isinstance(msg, bytes):
                        # 音频数据
                        audio_chunks += 1
                        if audio_chunks <= 3:
                            print(f"    📢 收到音频块 {audio_chunks}: {len(msg)} bytes")
                        elif audio_chunks == 4:
                            print(f"    📢 ...")
                    else:
                        data = json.loads(msg)
                        msg_type = data.get('type', 'unknown')
                        received_messages.append(data)
                        
                        if msg_type == 'transcription':
                            transcription = data.get('text', '')
                            print(f"    📝 转录: {transcription[:60]}...")
                        
                        elif msg_type == 'transcription_chunk':
                            text = data.get('text', '')
                            is_final = data.get('is_final', False)
                            print(f"    📝 转录块: {'[F]' if is_final else '[P]'} {text[:40]}...")
                        
                        elif msg_type == 'evaluation':
                            evaluation = data.get('data', {})
                            score = evaluation.get('overall_score', 'N/A')
                            level = evaluation.get('cefr_level', 'N/A')
                            print(f"    📊 评估: 分数={score}, 等级={level}")
                        
                        elif msg_type == 'response':
                            response = data.get('text', '')
                            print(f"    💬 AI回复: {response[:60]}...")
                        
                        elif msg_type == 'audio_chunk':
                            audio_chunks += 1
                            if audio_chunks <= 3:
                                print(f"    📢 收到音频块 {audio_chunks}")
                            elif audio_chunks == 4:
                                print(f"    📢 ...")
                        
                        elif msg_type == 'audio_end':
                            print(f"    🔊 音频结束 (共 {audio_chunks} 块)")
                            break
                        
                        elif msg_type == 'error':
                            print(f"    ❌ 错误: {data.get('message', 'unknown')}")
                            break
                        
                        elif msg_type == 'processing':
                            print(f"    ⏳ 处理中...")
                        
                        elif msg_type == 'state':
                            print(f"    🔄 状态: {data.get('state', 'unknown')}")
                        
                        else:
                            print(f"    📨 {msg_type}: {str(data)[:60]}...")
                            
                except asyncio.TimeoutError:
                    print("    ⏰ 等待消息超时，继续...")
                    continue
            
            # 总结
            print("\n" + "=" * 60)
            print("  测试结果")
            print("=" * 60)
            
            # 检查是否收到了 text_chunk（AI 流式回复）
            has_text_chunks = any(m.get('type') == 'text_chunk' for m in received_messages)
            
            results = {
                "连接成功": True,
                "转录收到": transcription is not None or any(m.get('type') == 'transcription_chunk' for m in received_messages),
                "评估收到": evaluation is not None,
                "AI回复收到": response is not None or has_text_chunks,
                "音频收到": audio_chunks > 0
            }
            
            all_pass = True
            for name, passed in results.items():
                status = "✅" if passed else "❌"
                print(f"  {status} {name}")
                if not passed:
                    all_pass = False
            
            print("-" * 60)
            if all_pass:
                print("  🎉 完整流程测试通过！")
            else:
                print("  ⚠️ 部分测试未通过")
            
            return all_pass
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    try:
        import websockets
    except ImportError:
        print("安装 websockets...")
        os.system("pip install websockets -q")
        import websockets
    
    success = await test_full_flow()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
