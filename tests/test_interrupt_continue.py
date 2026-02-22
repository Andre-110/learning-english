#!/usr/bin/env python3
"""
测试用户打断、继续说等复杂场景

测试场景：
1. 基础流程：用户说话 -> AI 回复
2. 用户打断：AI 说话时用户开始说话
3. 用户继续说：用户分段说话（中间有停顿）
4. 快速连续：用户快速连续发送多段音频
"""
import asyncio
import wave
import struct
import json
import os
import sys

sys.path.insert(0, '/home/ubuntu/learning_english')
from dotenv import load_dotenv
load_dotenv()

from services.minimax_tts import MiniMaxTTSService
from services.doubao_asr import DoubaoASR


async def generate_test_audio(text: str, output_path: str) -> str:
    """生成测试音频文件"""
    print(f"  生成音频: \"{text}\"")
    
    tts = MiniMaxTTSService()
    pcm_data = await tts._text_to_speech_async(text)
    
    # 重采样到 16kHz
    samples = []
    for i in range(0, len(pcm_data) - 1, 4):
        sample = struct.unpack('<h', pcm_data[i:i+2])[0]
        samples.append(sample)
    
    pcm_16k = struct.pack('<' + 'h' * len(samples), *samples)
    
    # 保存为 WAV
    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(pcm_16k)
    
    duration = len(pcm_16k) / 2 / 16000
    print(f"  已保存: {output_path} ({duration:.2f}s)")
    return output_path


async def transcribe_audio(wav_path: str) -> str:
    """使用豆包 ASR 转录音频"""
    with wave.open(wav_path, 'rb') as wav_file:
        pcm_data = wav_file.readframes(wav_file.getnframes())
    
    asr = DoubaoASR()
    transcripts = []
    
    async def on_transcript(text, is_final):
        transcripts.append((text, is_final))
    
    await asr.start_stream(on_transcript=on_transcript)
    
    # 分块发送
    chunk_size = 3200
    for i in range(0, len(pcm_data), chunk_size):
        chunk = pcm_data[i:i+chunk_size]
        await asr.send_audio(chunk)
        await asyncio.sleep(0.02)
    
    await asyncio.sleep(1)
    final = await asr.stop_stream()
    
    return final or (transcripts[-1][0] if transcripts else "")


async def test_basic_flow():
    """测试 1: 基础流程"""
    print("\n" + "=" * 60)
    print("测试 1: 基础流程 - 用户说话 -> ASR 识别")
    print("=" * 60)
    
    # 生成测试音频
    wav_path = "/tmp/test_basic.wav"
    await generate_test_audio("I enjoy learning English because it opens many doors.", wav_path)
    
    # 识别
    print("\n  开始识别...")
    result = await transcribe_audio(wav_path)
    print(f"\n  ✅ 识别结果: \"{result}\"")
    
    return bool(result)


async def test_user_interrupt():
    """测试 2: 用户打断场景"""
    print("\n" + "=" * 60)
    print("测试 2: 用户打断 - 模拟 AI 播放中用户开始说话")
    print("=" * 60)
    
    # 生成两段音频：模拟用户在 AI 说话时开始说
    wav1 = "/tmp/test_interrupt_1.wav"
    wav2 = "/tmp/test_interrupt_2.wav"
    
    await generate_test_audio("Wait, I want to say something.", wav1)
    await generate_test_audio("Actually, I think English is very useful.", wav2)
    
    # 模拟场景：快速连续发送两段
    print("\n  模拟快速连续发送...")
    
    asr = DoubaoASR()
    transcripts = []
    
    async def on_transcript(text, is_final):
        print(f"    -> \"{text}\" (final={is_final})")
        transcripts.append((text, is_final))
    
    await asr.start_stream(on_transcript=on_transcript)
    
    # 发送第一段
    print("\n  发送第一段音频...")
    with wave.open(wav1, 'rb') as wav_file:
        pcm1 = wav_file.readframes(wav_file.getnframes())
    
    chunk_size = 3200
    for i in range(0, len(pcm1), chunk_size):
        await asr.send_audio(pcm1[i:i+chunk_size])
        await asyncio.sleep(0.01)
    
    # 短暂停顿，然后立即发送第二段（模拟打断）
    await asyncio.sleep(0.2)
    
    print("  发送第二段音频（模拟打断）...")
    with wave.open(wav2, 'rb') as wav_file:
        pcm2 = wav_file.readframes(wav_file.getnframes())
    
    for i in range(0, len(pcm2), chunk_size):
        await asr.send_audio(pcm2[i:i+chunk_size])
        await asyncio.sleep(0.01)
    
    await asyncio.sleep(1.5)
    final = await asr.stop_stream()
    
    print(f"\n  ✅ 最终识别: \"{final}\"")
    return bool(final)


async def test_user_continue():
    """测试 3: 用户继续说（分段说话）"""
    print("\n" + "=" * 60)
    print("测试 3: 用户继续说 - 用户分段说话，中间有停顿")
    print("=" * 60)
    
    # 生成三段音频
    segments = [
        ("My name is John.", "/tmp/test_cont_1.wav"),
        ("I am from Beijing.", "/tmp/test_cont_2.wav"),
        ("I like to travel.", "/tmp/test_cont_3.wav"),
    ]
    
    for text, path in segments:
        await generate_test_audio(text, path)
    
    # 模拟分段发送，中间有较长停顿
    print("\n  模拟分段发送（中间有停顿）...")
    
    asr = DoubaoASR()
    transcripts = []
    
    async def on_transcript(text, is_final):
        print(f"    -> \"{text}\" (final={is_final})")
        transcripts.append((text, is_final))
    
    await asr.start_stream(on_transcript=on_transcript)
    
    chunk_size = 3200
    
    for i, (text, path) in enumerate(segments):
        print(f"\n  发送第 {i+1} 段: \"{text}\"")
        
        with wave.open(path, 'rb') as wav_file:
            pcm = wav_file.readframes(wav_file.getnframes())
        
        for j in range(0, len(pcm), chunk_size):
            await asr.send_audio(pcm[j:j+chunk_size])
            await asyncio.sleep(0.02)
        
        if i < len(segments) - 1:
            # 模拟用户思考/停顿
            print("  ... 停顿 1 秒 ...")
            await asyncio.sleep(1.0)
    
    await asyncio.sleep(1.5)
    final = await asr.stop_stream()
    
    print(f"\n  ✅ 最终识别: \"{final}\"")
    
    # 检查是否识别了所有段落
    all_text = " ".join([t for t, _ in segments])
    print(f"  预期内容: \"{all_text}\"")
    
    return bool(final)


async def test_rapid_fire():
    """测试 4: 快速连续发送"""
    print("\n" + "=" * 60)
    print("测试 4: 快速连续 - 模拟用户快速说话")
    print("=" * 60)
    
    # 生成一段较长的音频
    text = "One two three four five six seven eight nine ten."
    wav_path = "/tmp/test_rapid.wav"
    await generate_test_audio(text, wav_path)
    
    print("\n  开始快速发送音频块...")
    
    asr = DoubaoASR()
    transcripts = []
    
    async def on_transcript(text, is_final):
        print(f"    -> \"{text}\" (final={is_final})")
        transcripts.append((text, is_final))
    
    await asr.start_stream(on_transcript=on_transcript)
    
    with wave.open(wav_path, 'rb') as wav_file:
        pcm = wav_file.readframes(wav_file.getnframes())
    
    # 快速发送，几乎不等待
    chunk_size = 1600  # 更小的块
    for i in range(0, len(pcm), chunk_size):
        await asr.send_audio(pcm[i:i+chunk_size])
        await asyncio.sleep(0.005)  # 5ms
    
    await asyncio.sleep(1.5)
    final = await asr.stop_stream()
    
    print(f"\n  ✅ 最终识别: \"{final}\"")
    return bool(final)


async def test_websocket_session():
    """测试 5: 完整 WebSocket 会话"""
    print("\n" + "=" * 60)
    print("测试 5: 完整 WebSocket 会话（连接后端服务）")
    print("=" * 60)
    
    import websockets
    import requests
    
    # 1. 创建对话
    print("\n  1. 创建对话...")
    try:
        resp = requests.post(
            "http://localhost:8000/conversations/start",
            json={"user_id": "test_interrupt_user"},
            timeout=10
        )
        if resp.status_code != 200:
            print(f"  ❌ 创建对话失败: {resp.status_code}")
            return False
        
        data = resp.json()
        conversation_id = data["conversation_id"]
        print(f"  ✅ 对话 ID: {conversation_id}")
        initial_q = data.get('initial_question') or ''
        if initial_q:
            print(f"  初始问题: {initial_q[:80]}...")
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return False
    
    # 2. 生成测试音频
    print("\n  2. 生成测试音频...")
    wav_path = "/tmp/test_ws_session.wav"
    await generate_test_audio("I think learning English is very important for my career.", wav_path)
    
    with wave.open(wav_path, 'rb') as wav_file:
        pcm_data = wav_file.readframes(wav_file.getnframes())
    
    # 3. 连接 WebSocket
    print("\n  3. 连接 WebSocket...")
    ws_url = f"ws://localhost:8000/streaming-voice/chat?user_id={conversation_id}"
    
    try:
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            # 等待连接确认
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            print(f"  收到: {data.get('type')} - {data.get('message', '')[:50]}")
            
            # 发送 start
            await ws.send(json.dumps({"type": "start"}))
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            print(f"  收到: {data.get('type')} - {data.get('message', '')[:50]}")
            
            # 发送音频
            print("\n  4. 发送音频...")
            chunk_size = 4096
            for i in range(0, len(pcm_data), chunk_size):
                await ws.send(pcm_data[i:i+chunk_size])
                await asyncio.sleep(0.02)
            
            # 发送结束
            await ws.send(json.dumps({"type": "audio_end"}))
            print("  音频发送完成")
            
            # 接收响应
            print("\n  5. 接收响应...")
            responses = []
            for _ in range(30):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15)
                    if isinstance(msg, str):
                        data = json.loads(msg)
                        msg_type = data.get("type")
                        
                        if msg_type == "transcription":
                            print(f"    转录: {data.get('text', '')[:60]}...")
                        elif msg_type == "evaluation":
                            eval_data = data.get("data", {})
                            score = eval_data.get("overall_score", "?")
                            print(f"    评估: 分数={score}")
                        elif msg_type == "response":
                            print(f"    回复: {data.get('text', '')[:60]}...")
                        elif msg_type == "audio_chunk":
                            responses.append("audio")
                        elif msg_type == "audio_end":
                            print(f"    音频播放完成 (收到 {len([r for r in responses if r == 'audio'])} 个音频块)")
                            break
                        elif msg_type == "error":
                            print(f"    ❌ 错误: {data.get('message')}")
                            break
                except asyncio.TimeoutError:
                    print("    超时")
                    break
            
            print("\n  ✅ WebSocket 会话完成")
            return True
            
    except Exception as e:
        print(f"  ❌ WebSocket 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("用户打断/继续说场景测试")
    print("=" * 60)
    
    results = {}
    
    # 运行测试
    try:
        results["基础流程"] = await test_basic_flow()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results["基础流程"] = False
    
    try:
        results["用户打断"] = await test_user_interrupt()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results["用户打断"] = False
    
    try:
        results["用户继续说"] = await test_user_continue()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results["用户继续说"] = False
    
    try:
        results["快速连续"] = await test_rapid_fire()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results["快速连续"] = False
    
    try:
        results["WebSocket会话"] = await test_websocket_session()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results["WebSocket会话"] = False
    
    # 打印总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n  总计: {passed}/{total} 通过")
    
    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
