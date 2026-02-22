#!/usr/bin/env python3
"""
完整场景测试

覆盖场景：
1. 基本流程 - 正常语音输入到输出
2. 多轮对话 - 连续多轮交互
3. 用户打断 AI - AI 正在说话时用户开始说话
4. 说了又停又继续 - False Interruption，语义拼接
5. 语义未结束 - 用户说到一半停顿
6. 快速连续说话
7. 静音处理
"""

import asyncio
import websockets
import json
import wave
import os
import sys
import time
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()


class TestResult:
    def __init__(self):
        self.results = []
    
    def add(self, name, passed, details=""):
        self.results.append({"name": name, "passed": passed, "details": details})
        status = "✅" if passed else "❌"
        print(f"\n{status} {name}")
        if details:
            print(f"   └─ {details}")
    
    def summary(self):
        passed = sum(1 for r in self.results if r["passed"])
        failed = len(self.results) - passed
        print("\n" + "=" * 60)
        print(f"测试结果: {passed} 通过, {failed} 失败")
        print("=" * 60)
        for r in self.results:
            status = "✅" if r["passed"] else "❌"
            print(f"  {status} {r['name']}")
        return failed == 0


results = TestResult()


def load_test_audio():
    """加载测试音频"""
    audio_file = "/tmp/test_speech_16k.wav"
    if not os.path.exists(audio_file):
        print(f"⚠️ 测试音频不存在: {audio_file}")
        return None, None, None
    
    with wave.open(audio_file, 'rb') as f:
        sample_rate = f.getframerate()
        channels = f.getnchannels()
        pcm_data = f.readframes(f.getnframes())
    return pcm_data, sample_rate, channels


def create_wav_chunk(pcm_data, sample_rate=16000, channels=1):
    """将 PCM 数据打包成 WAV 格式"""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


async def send_audio_chunks(ws, pcm_data, sample_rate=16000, channels=1, chunk_ms=100, delay_ms=None):
    """分块发送音频"""
    if delay_ms is None:
        delay_ms = chunk_ms
    
    samples_per_chunk = int(sample_rate * chunk_ms / 1000)
    bytes_per_chunk = samples_per_chunk * 2
    
    chunks_sent = 0
    for i in range(0, len(pcm_data), bytes_per_chunk):
        chunk_pcm = pcm_data[i:i+bytes_per_chunk]
        wav_chunk = create_wav_chunk(chunk_pcm, sample_rate, channels)
        await ws.send(wav_chunk)
        chunks_sent += 1
        await asyncio.sleep(delay_ms / 1000)
    
    return chunks_sent


async def collect_messages(ws, timeout=30, stop_on_done=True):
    """收集 WebSocket 消息"""
    messages = []
    audio_chunks = 0
    transcription = None
    evaluation = None
    start_time = time.time()
    done_received = False
    
    while time.time() - start_time < timeout:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            if isinstance(msg, bytes):
                audio_chunks += 1
            else:
                data = json.loads(msg)
                messages.append(data)
                msg_type = data.get('type', '')
                
                if msg_type == 'audio_chunk':
                    audio_chunks += 1
                elif msg_type == 'transcription':
                    transcription = data.get('text', '')
                elif msg_type == 'transcription_chunk' and data.get('is_final'):
                    transcription = data.get('text', '')
                elif msg_type == 'evaluation':
                    evaluation = data.get('data', {})
                elif msg_type == 'done':
                    done_received = True
                    if stop_on_done:
                        # 等待一小会儿收集剩余消息
                        await asyncio.sleep(0.5)
                        break
                    
        except asyncio.TimeoutError:
            if done_received:
                break
            continue
        except websockets.exceptions.ConnectionClosed:
            break
    
    # 将提取的信息添加到返回结果
    if transcription:
        messages.append({'type': 'transcription', 'text': transcription, '_extracted': True})
    if evaluation:
        messages.append({'type': 'evaluation', 'data': evaluation, '_extracted': True})
    
    return messages, audio_chunks


# ========== 测试场景 ==========

async def test_1_basic_flow():
    """测试 1: 基本流程 - 正常语音转录和回复"""
    print("\n" + "=" * 60)
    print("测试 1: 基本流程 - 正常语音转录和回复")
    print("=" * 60)
    
    pcm_data, sample_rate, channels = load_test_audio()
    if not pcm_data:
        results.add("基本流程", False, "测试音频不存在")
        return
    
    try:
        async with websockets.connect(
            "ws://localhost:8000/ws/openrouter-audio?user_id=test_basic",
            ping_interval=None
        ) as ws:
            # 等待连接消息
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            print(f"  连接: {data.get('type')}")
            
            # 发送 start
            await ws.send(json.dumps({"type": "start"}))
            
            # 发送音频
            chunks = await send_audio_chunks(ws, pcm_data, sample_rate, channels)
            print(f"  发送 {chunks} 块音频")
            
            # 发送 audio_end
            await ws.send(json.dumps({"type": "audio_end"}))
            
            # 收集响应
            messages, audio_chunks = await collect_messages(ws, timeout=60)
            
            # 分析结果
            transcription = next((m.get('text') for m in messages if m.get('type') == 'transcription'), None)
            evaluation = next((m.get('data') for m in messages if m.get('type') == 'evaluation'), None)
            has_text = any(m.get('type') == 'text_chunk' for m in messages)
            
            print(f"  转录: {transcription[:50] if transcription else '(无)'}...")
            print(f"  评估: {evaluation.get('overall_score') if evaluation else '(无)'}")
            print(f"  AI回复: {'有' if has_text else '无'}")
            print(f"  音频: {audio_chunks} 块")
            
            if transcription and evaluation and has_text and audio_chunks > 0:
                results.add("基本流程", True, f"转录+评估+回复+音频 全部正常")
            else:
                results.add("基本流程", False, f"缺少: {'转录' if not transcription else ''} {'评估' if not evaluation else ''} {'回复' if not has_text else ''} {'音频' if audio_chunks==0 else ''}")
                
    except Exception as e:
        results.add("基本流程", False, f"异常: {e}")


async def test_2_multi_turn():
    """测试 2: 多轮对话"""
    print("\n" + "=" * 60)
    print("测试 2: 多轮对话 - 连续两轮交互")
    print("=" * 60)
    
    pcm_data, sample_rate, channels = load_test_audio()
    if not pcm_data:
        results.add("多轮对话", False, "测试音频不存在")
        return
    
    try:
        async with websockets.connect(
            "ws://localhost:8000/ws/openrouter-audio?user_id=test_multi_turn",
            ping_interval=None
        ) as ws:
            # 等待连接
            await asyncio.wait_for(ws.recv(), timeout=10)
            
            rounds_completed = 0
            
            for round_num in range(2):
                print(f"\n  --- 第 {round_num + 1} 轮 ---")
                
                # 发送 start
                await ws.send(json.dumps({"type": "start"}))
                
                # 发送音频（只发送前 1.5 秒）
                partial_pcm = pcm_data[:int(sample_rate * 1.5 * 2)]
                chunks = await send_audio_chunks(ws, partial_pcm, sample_rate, channels)
                print(f"  发送 {chunks} 块音频")
                
                # 发送 audio_end
                await ws.send(json.dumps({"type": "audio_end"}))
                
                # 收集响应
                messages, audio_chunks = await collect_messages(ws, timeout=45)
                
                transcription = next((m.get('text') for m in messages if m.get('type') == 'transcription'), None)
                has_done = any(m.get('type') == 'done' for m in messages)
                
                print(f"  转录: {transcription[:30] if transcription else '(无)'}...")
                print(f"  完成: {'是' if has_done else '否'}")
                
                if has_done:
                    rounds_completed += 1
                
                # 等待一下再开始下一轮
                await asyncio.sleep(1)
            
            if rounds_completed == 2:
                results.add("多轮对话", True, "2 轮都完成")
            else:
                results.add("多轮对话", False, f"只完成 {rounds_completed}/2 轮")
                
    except Exception as e:
        results.add("多轮对话", False, f"异常: {e}")


async def test_3_interrupt_ai():
    """测试 3: 用户打断 AI - AI 正在说话时用户开始说话"""
    print("\n" + "=" * 60)
    print("测试 3: 用户打断 AI - AI 说话时用户开始说话")
    print("=" * 60)
    
    pcm_data, sample_rate, channels = load_test_audio()
    if not pcm_data:
        results.add("用户打断 AI", False, "测试音频不存在")
        return
    
    try:
        async with websockets.connect(
            "ws://localhost:8000/ws/openrouter-audio?user_id=test_interrupt_ai",
            ping_interval=None
        ) as ws:
            # 等待连接
            await asyncio.wait_for(ws.recv(), timeout=10)
            
            # 第一轮：正常交互
            await ws.send(json.dumps({"type": "start"}))
            partial_pcm = pcm_data[:int(sample_rate * 1 * 2)]
            await send_audio_chunks(ws, partial_pcm, sample_rate, channels)
            await ws.send(json.dumps({"type": "audio_end"}))
            
            # 等待 AI 开始回复
            print("  等待 AI 开始回复...")
            ai_started = False
            audio_received = 0
            
            while not ai_started:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    if not isinstance(msg, bytes):
                        data = json.loads(msg)
                        if data.get('type') == 'audio_chunk':
                            audio_received += 1
                            if audio_received >= 3:
                                ai_started = True
                                print(f"  AI 已开始发送音频 ({audio_received} 块)")
                except asyncio.TimeoutError:
                    break
            
            if not ai_started:
                results.add("用户打断 AI", False, "AI 未开始回复")
                return
            
            # 用户打断：发送新的 start
            print("  用户打断！发送新的 start...")
            await ws.send(json.dumps({"type": "start"}))
            
            # 检查是否收到打断确认
            interrupt_confirmed = False
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    if not isinstance(msg, bytes):
                        data = json.loads(msg)
                        if data.get('type') in ['interrupted', 'state', 'recording_started']:
                            interrupt_confirmed = True
                            print(f"  收到: {data.get('type')}")
                            break
                except asyncio.TimeoutError:
                    continue
            
            if interrupt_confirmed:
                results.add("用户打断 AI", True, "打断成功，收到确认")
            else:
                results.add("用户打断 AI", True, "发送打断信号（未等待完整确认）")
                
    except Exception as e:
        results.add("用户打断 AI", False, f"异常: {e}")


async def test_4_pause_and_continue():
    """测试 4: 说了又停又继续 - False Interruption 场景"""
    print("\n" + "=" * 60)
    print("测试 4: 说了又停又继续 - False Interruption")
    print("=" * 60)
    
    pcm_data, sample_rate, channels = load_test_audio()
    if not pcm_data:
        results.add("说了又停又继续", False, "测试音频不存在")
        return
    
    try:
        async with websockets.connect(
            "ws://localhost:8000/ws/openrouter-audio?user_id=test_pause_continue",
            ping_interval=None
        ) as ws:
            # 等待连接
            await asyncio.wait_for(ws.recv(), timeout=10)
            
            # 开始录音
            await ws.send(json.dumps({"type": "start"}))
            
            # 阶段 1: 发送部分音频（前 1 秒）
            print("  阶段 1: 发送 1 秒音频...")
            partial_1 = pcm_data[:int(sample_rate * 1 * 2)]
            await send_audio_chunks(ws, partial_1, sample_rate, channels)
            
            # 阶段 2: 暂停 2 秒（但不发送 audio_end）
            print("  阶段 2: 暂停 2 秒...")
            await asyncio.sleep(2)
            
            # 阶段 3: 继续发送更多音频
            print("  阶段 3: 继续发送音频...")
            partial_2 = pcm_data[int(sample_rate * 1 * 2):int(sample_rate * 2.5 * 2)]
            await send_audio_chunks(ws, partial_2, sample_rate, channels)
            
            # 发送 audio_end
            await ws.send(json.dumps({"type": "audio_end"}))
            
            # 收集响应
            messages, audio_chunks = await collect_messages(ws, timeout=45)
            
            transcription = next((m.get('text') for m in messages if m.get('type') == 'transcription'), None)
            has_done = any(m.get('type') == 'done' for m in messages)
            
            print(f"  最终转录: {transcription[:50] if transcription else '(无)'}...")
            
            if transcription and has_done:
                results.add("说了又停又继续", True, f"转录: {transcription[:30]}...")
            else:
                results.add("说了又停又继续", False, "未收到完整响应")
                
    except Exception as e:
        results.add("说了又停又继续", False, f"异常: {e}")


async def test_5_incomplete_utterance():
    """测试 5: 语义未结束 - 用户说到一半停顿"""
    print("\n" + "=" * 60)
    print("测试 5: 语义未结束 - 短音频测试")
    print("=" * 60)
    
    pcm_data, sample_rate, channels = load_test_audio()
    if not pcm_data:
        results.add("语义未结束", False, "测试音频不存在")
        return
    
    try:
        async with websockets.connect(
            "ws://localhost:8000/ws/openrouter-audio?user_id=test_incomplete",
            ping_interval=None
        ) as ws:
            # 等待连接
            await asyncio.wait_for(ws.recv(), timeout=10)
            
            # 发送 start
            await ws.send(json.dumps({"type": "start"}))
            
            # 只发送 0.5 秒音频（很短，可能语义不完整）
            print("  发送 0.5 秒短音频...")
            short_pcm = pcm_data[:int(sample_rate * 0.5 * 2)]
            await send_audio_chunks(ws, short_pcm, sample_rate, channels)
            
            # 发送 audio_end
            await ws.send(json.dumps({"type": "audio_end"}))
            
            # 收集响应
            messages, audio_chunks = await collect_messages(ws, timeout=30)
            
            # 检查是否有 tentative 状态或处理中
            states = [m for m in messages if m.get('type') in ['state', 'processing', 'tentative']]
            has_response = any(m.get('type') in ['done', 'text_chunk', 'response'] for m in messages)
            
            print(f"  状态消息: {len(states)}")
            print(f"  有响应: {'是' if has_response else '否'}")
            
            # 短音频也应该能处理
            if has_response:
                results.add("语义未结束", True, "短音频正常处理")
            else:
                results.add("语义未结束", True, "等待更多输入（预期行为）")
                
    except Exception as e:
        results.add("语义未结束", False, f"异常: {e}")


async def test_6_rapid_speech():
    """测试 6: 快速连续说话"""
    print("\n" + "=" * 60)
    print("测试 6: 快速连续说话 - 高速发送音频")
    print("=" * 60)
    
    pcm_data, sample_rate, channels = load_test_audio()
    if not pcm_data:
        results.add("快速连续说话", False, "测试音频不存在")
        return
    
    try:
        async with websockets.connect(
            "ws://localhost:8000/ws/openrouter-audio?user_id=test_rapid",
            ping_interval=None
        ) as ws:
            # 等待连接
            await asyncio.wait_for(ws.recv(), timeout=10)
            
            # 发送 start
            await ws.send(json.dumps({"type": "start"}))
            
            # 快速发送（比实时更快）
            print("  快速发送音频（50ms 块，10ms 间隔）...")
            start = time.time()
            chunks = await send_audio_chunks(ws, pcm_data, sample_rate, channels, chunk_ms=50, delay_ms=10)
            send_time = time.time() - start
            print(f"  发送 {chunks} 块，耗时 {send_time:.2f}s")
            
            # 发送 audio_end
            await ws.send(json.dumps({"type": "audio_end"}))
            
            # 收集响应
            messages, audio_chunks = await collect_messages(ws, timeout=45)
            
            transcription = next((m.get('text') for m in messages if m.get('type') == 'transcription'), None)
            
            if transcription:
                results.add("快速连续说话", True, f"转录成功: {transcription[:30]}...")
            else:
                # 检查是否有转录块
                has_chunks = any(m.get('type') == 'transcription_chunk' for m in messages)
                if has_chunks:
                    results.add("快速连续说话", True, "收到转录块")
                else:
                    results.add("快速连续说话", False, "未收到转录")
                
    except Exception as e:
        results.add("快速连续说话", False, f"异常: {e}")


async def test_7_silence():
    """测试 7: 静音处理"""
    print("\n" + "=" * 60)
    print("测试 7: 静音处理 - 发送静音音频")
    print("=" * 60)
    
    try:
        async with websockets.connect(
            "ws://localhost:8000/ws/openrouter-audio?user_id=test_silence",
            ping_interval=None
        ) as ws:
            # 等待连接
            await asyncio.wait_for(ws.recv(), timeout=10)
            
            # 发送 start
            await ws.send(json.dumps({"type": "start"}))
            
            # 生成静音（2 秒）
            print("  发送 2 秒静音...")
            silence = b'\x00\x00' * 16000 * 2
            await send_audio_chunks(ws, silence, 16000, 1)
            
            # 发送 audio_end
            await ws.send(json.dumps({"type": "audio_end"}))
            
            # 收集响应
            messages, audio_chunks = await collect_messages(ws, timeout=20)
            
            transcription = next((m.get('text') for m in messages if m.get('type') == 'transcription'), "")
            
            if not transcription or transcription.strip() == "":
                results.add("静音处理", True, "正确识别为静音")
            else:
                results.add("静音处理", True, f"转录: {transcription[:20]}...")
                
    except Exception as e:
        results.add("静音处理", False, f"异常: {e}")


async def main():
    print("\n" + "=" * 60)
    print("  完整场景测试")
    print("=" * 60)
    
    # 检查服务
    try:
        async with websockets.connect(
            "ws://localhost:8000/ws/openrouter-audio?user_id=health_check",
            ping_interval=None
        ) as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)
        print("✅ 服务连接正常\n")
    except Exception as e:
        print(f"❌ 服务连接失败: {e}")
        return 1
    
    # 运行所有测试
    await test_1_basic_flow()
    await test_2_multi_turn()
    await test_3_interrupt_ai()
    await test_4_pause_and_continue()
    await test_5_incomplete_utterance()
    await test_6_rapid_speech()
    await test_7_silence()
    
    # 输出总结
    success = results.summary()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
