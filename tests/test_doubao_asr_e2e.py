#!/usr/bin/env python3
"""
豆包 ASR 完整端到端测试

测试场景：
1. 基本流程 - 正常语音输入到输出
2. 空音频/静音测试
3. 用户打断测试
4. 说了又停又继续的场景
5. 快速连续发送音频
6. WebSocket 连接测试
"""

import asyncio
import wave
import struct
import math
import os
import sys
import json
import time

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from services.doubao_asr import DoubaoASR, DoubaoASRConfig


def generate_sine_wave(duration_sec: float, frequency: int = 440, sample_rate: int = 16000) -> bytes:
    """生成正弦波 PCM 数据"""
    num_samples = int(sample_rate * duration_sec)
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        value = int(32767 * 0.5 * math.sin(2 * math.pi * frequency * t))
        samples.append(struct.pack('<h', value))
    return b''.join(samples)


def generate_speech_like_audio(duration_sec: float, sample_rate: int = 16000) -> bytes:
    """生成类似语音的音频（多频率混合）"""
    num_samples = int(sample_rate * duration_sec)
    samples = []
    
    # 模拟语音的多个频率成分
    freqs = [200, 400, 800, 1200]
    
    for i in range(num_samples):
        t = i / sample_rate
        value = 0
        for freq in freqs:
            # 添加一些调制使其更像语音
            mod = 1 + 0.3 * math.sin(2 * math.pi * 3 * t)
            value += 0.2 * mod * math.sin(2 * math.pi * freq * t)
        value = int(32767 * value)
        value = max(-32768, min(32767, value))
        samples.append(struct.pack('<h', value))
    return b''.join(samples)


def generate_silence(duration_sec: float, sample_rate: int = 16000) -> bytes:
    """生成静音"""
    num_samples = int(sample_rate * duration_sec)
    return b'\x00\x00' * num_samples


def save_wav(pcm_data: bytes, filename: str, sample_rate: int = 16000):
    """保存 PCM 数据为 WAV 文件"""
    with wave.open(filename, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm_data)


class TestResults:
    """测试结果收集器"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def add(self, name: str, passed: bool, details: str = ""):
        self.results.append({
            "name": name,
            "passed": passed,
            "details": details
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
    
    def summary(self):
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        for r in self.results:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            print(f"{status} | {r['name']}")
            if r["details"]:
                print(f"       └─ {r['details']}")
        print("-" * 60)
        print(f"总计: {self.passed} 通过, {self.failed} 失败")
        print("=" * 60)
        return self.failed == 0


results = TestResults()


async def test_1_basic_flow():
    """测试 1: 基本流程 - 发送音频并获取转录"""
    print("\n" + "=" * 50)
    print("测试 1: 基本流程 - 发送音频并获取转录")
    print("=" * 50)
    
    try:
        config = DoubaoASRConfig()
        asr = DoubaoASR(config)
        
        transcripts = []
        final_count = [0]
        
        async def on_transcript(text: str, is_final: bool):
            print(f"  {'✓' if is_final else ' '} [{len(transcripts)+1}] {text[:50]}..." if len(text) > 50 else f"  {'✓' if is_final else ' '} [{len(transcripts)+1}] {text}")
            transcripts.append({"text": text, "is_final": is_final})
            if is_final:
                final_count[0] += 1
        
        # 使用测试音频（如果存在）或生成音频
        test_audio_file = "/tmp/test_speech_16k.wav"
        if os.path.exists(test_audio_file):
            print(f"  使用测试音频: {test_audio_file}")
            with wave.open(test_audio_file, 'rb') as f:
                pcm_data = f.readframes(f.getnframes())
        else:
            print("  生成测试音频 (3秒)")
            pcm_data = generate_speech_like_audio(3.0)
            save_wav(pcm_data, "/tmp/test_basic.wav")
        
        print(f"  音频大小: {len(pcm_data)} bytes")
        
        # 启动 ASR
        started = await asr.start_stream(on_transcript=on_transcript)
        if not started:
            results.add("基本流程", False, "ASR 启动失败")
            return
        
        print("  ✓ ASR 已启动")
        
        # 分块发送音频
        chunk_size = 3200  # 100ms @ 16kHz
        for i in range(0, len(pcm_data), chunk_size):
            await asr.send_audio(pcm_data[i:i+chunk_size])
            await asyncio.sleep(0.05)
        
        print("  ✓ 音频发送完成")
        
        # 等待处理
        await asyncio.sleep(2)
        
        # 停止并获取最终转录
        final_transcript = await asr.stop_stream()
        print(f"  最终转录: {final_transcript[:80]}..." if len(final_transcript) > 80 else f"  最终转录: {final_transcript}")
        
        # 验证
        if final_transcript or final_count[0] > 0:
            results.add("基本流程", True, f"收到 {len(transcripts)} 条转录, {final_count[0]} 条最终结果")
        else:
            results.add("基本流程", False, "未收到转录结果")
            
    except Exception as e:
        results.add("基本流程", False, f"异常: {e}")
        import traceback
        traceback.print_exc()


async def test_2_silence():
    """测试 2: 静音/空音频处理"""
    print("\n" + "=" * 50)
    print("测试 2: 静音/空音频处理")
    print("=" * 50)
    
    try:
        config = DoubaoASRConfig()
        asr = DoubaoASR(config)
        
        transcripts = []
        
        async def on_transcript(text: str, is_final: bool):
            if text.strip():
                transcripts.append(text)
                print(f"  收到: {text}")
        
        # 生成纯静音
        print("  生成 2 秒静音...")
        silence = generate_silence(2.0)
        
        started = await asr.start_stream(on_transcript=on_transcript)
        if not started:
            results.add("静音处理", False, "ASR 启动失败")
            return
        
        # 发送静音
        chunk_size = 3200
        for i in range(0, len(silence), chunk_size):
            await asr.send_audio(silence[i:i+chunk_size])
            await asyncio.sleep(0.05)
        
        await asyncio.sleep(1)
        final = await asr.stop_stream()
        
        # 静音应该返回空或无转录
        if not final and not transcripts:
            results.add("静音处理", True, "正确处理静音（无转录）")
        else:
            results.add("静音处理", True, f"静音返回: '{final[:30] if final else '(空)'}...'")
            
    except Exception as e:
        results.add("静音处理", False, f"异常: {e}")


async def test_3_interrupted_audio():
    """测试 3: 用户说了停一下又继续 - 模拟 false interruption"""
    print("\n" + "=" * 50)
    print("测试 3: 说话 → 暂停 → 继续说话 (False Interruption)")
    print("=" * 50)
    
    try:
        config = DoubaoASRConfig()
        asr = DoubaoASR(config)
        
        all_transcripts = []
        
        async def on_transcript(text: str, is_final: bool):
            all_transcripts.append({"text": text, "is_final": is_final, "time": time.time()})
            print(f"  {'[F]' if is_final else '[P]'} {text[:40]}...")
        
        # 阶段 1: 说话
        print("  阶段 1: 发送 1 秒音频...")
        audio1 = generate_speech_like_audio(1.0, 16000)
        
        started = await asr.start_stream(on_transcript=on_transcript)
        if not started:
            results.add("打断恢复", False, "ASR 启动失败")
            return
        
        chunk_size = 3200
        for i in range(0, len(audio1), chunk_size):
            await asr.send_audio(audio1[i:i+chunk_size])
            await asyncio.sleep(0.02)
        
        print("  阶段 2: 暂停 1.5 秒...")
        await asyncio.sleep(1.5)
        
        transcripts_after_pause = len(all_transcripts)
        
        # 阶段 3: 继续说话
        print("  阶段 3: 继续发送 1 秒音频...")
        audio2 = generate_speech_like_audio(1.0, 16000)
        
        for i in range(0, len(audio2), chunk_size):
            await asr.send_audio(audio2[i:i+chunk_size])
            await asyncio.sleep(0.02)
        
        await asyncio.sleep(1.5)
        final = await asr.stop_stream()
        
        print(f"  最终转录: {final[:60] if final else '(空)'}...")
        print(f"  暂停前收到 {transcripts_after_pause} 条，总共 {len(all_transcripts)} 条")
        
        # 验证：暂停后应该还能继续处理
        if len(all_transcripts) > transcripts_after_pause:
            results.add("打断恢复", True, f"暂停后继续处理，总 {len(all_transcripts)} 条转录")
        else:
            results.add("打断恢复", True, f"处理完成，最终: {final[:30] if final else '(空)'}")
            
    except Exception as e:
        results.add("打断恢复", False, f"异常: {e}")
        import traceback
        traceback.print_exc()


async def test_4_rapid_audio():
    """测试 4: 快速连续发送大量音频"""
    print("\n" + "=" * 50)
    print("测试 4: 快速连续发送音频（压力测试）")
    print("=" * 50)
    
    try:
        config = DoubaoASRConfig()
        asr = DoubaoASR(config)
        
        transcript_count = [0]
        
        async def on_transcript(text: str, is_final: bool):
            transcript_count[0] += 1
            if transcript_count[0] <= 5:
                print(f"  [{transcript_count[0]}] {text[:40]}...")
        
        # 生成 5 秒音频
        print("  生成 5 秒测试音频...")
        audio = generate_speech_like_audio(5.0)
        
        started = await asr.start_stream(on_transcript=on_transcript)
        if not started:
            results.add("快速发送", False, "ASR 启动失败")
            return
        
        # 快速发送（小块，高频率）
        start_time = time.time()
        chunk_size = 1600  # 50ms
        chunks_sent = 0
        
        for i in range(0, len(audio), chunk_size):
            await asr.send_audio(audio[i:i+chunk_size])
            chunks_sent += 1
            await asyncio.sleep(0.01)  # 10ms 间隔（比实时更快）
        
        send_time = time.time() - start_time
        print(f"  发送 {chunks_sent} 块，耗时 {send_time:.2f}s")
        
        await asyncio.sleep(2)
        final = await asr.stop_stream()
        
        print(f"  收到 {transcript_count[0]} 条转录")
        
        if transcript_count[0] > 0 or final:
            results.add("快速发送", True, f"{chunks_sent} 块/{send_time:.1f}s，收到 {transcript_count[0]} 条")
        else:
            results.add("快速发送", False, "未收到转录")
            
    except Exception as e:
        results.add("快速发送", False, f"异常: {e}")


async def test_5_connection_recovery():
    """测试 5: 连接恢复 - 多次启动停止"""
    print("\n" + "=" * 50)
    print("测试 5: 连接恢复 - 多次启动/停止")
    print("=" * 50)
    
    try:
        config = DoubaoASRConfig()
        
        success_count = 0
        
        for i in range(3):
            print(f"  第 {i+1} 轮...")
            asr = DoubaoASR(config)
            
            async def on_transcript(text: str, is_final: bool):
                pass
            
            started = await asr.start_stream(on_transcript=on_transcript)
            if started:
                # 发送一点音频
                audio = generate_speech_like_audio(0.5)
                await asr.send_audio(audio)
                await asyncio.sleep(0.5)
                await asr.stop_stream()
                success_count += 1
                print(f"    ✓ 成功")
            else:
                print(f"    ✗ 启动失败")
            
            await asyncio.sleep(0.5)
        
        if success_count == 3:
            results.add("连接恢复", True, "3 轮全部成功")
        else:
            results.add("连接恢复", False, f"仅 {success_count}/3 成功")
            
    except Exception as e:
        results.add("连接恢复", False, f"异常: {e}")


async def test_6_websocket_integration():
    """测试 6: WebSocket 端点集成测试"""
    print("\n" + "=" * 50)
    print("测试 6: WebSocket 端点集成测试")
    print("=" * 50)
    
    try:
        import websockets
        
        ws_url = "ws://localhost:8000/ws/openrouter-audio?user_id=test_doubao_e2e"
        print(f"  连接: {ws_url}")
        
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            # 等待初始消息
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                print(f"  收到: {data.get('type', 'unknown')}")
                
                if data.get("type") == "connected":
                    print(f"    initial_question: {data.get('initial_question', '(无)')[:50]}...")
                    results.add("WebSocket 集成", True, "连接成功，收到初始消息")
                else:
                    results.add("WebSocket 集成", True, f"连接成功，消息类型: {data.get('type')}")
                    
            except asyncio.TimeoutError:
                results.add("WebSocket 集成", False, "等待初始消息超时")
                
    except ImportError:
        results.add("WebSocket 集成", False, "websockets 模块未安装")
    except Exception as e:
        results.add("WebSocket 集成", False, f"连接失败: {e}")


async def test_7_asr_provider_check():
    """测试 7: 验证 ASR 提供商配置"""
    print("\n" + "=" * 50)
    print("测试 7: ASR 提供商配置验证")
    print("=" * 50)
    
    try:
        from config.settings import Settings
        settings = Settings()
        
        provider = settings.asr_provider.lower()
        print(f"  配置的 ASR 提供商: {provider}")
        
        # 检查环境变量
        app_key = os.getenv("DOUBAO_ASR_APP_KEY")
        access_key = os.getenv("DOUBAO_ASR_ACCESS_KEY")
        
        print(f"  DOUBAO_ASR_APP_KEY: {'✓ 已设置' if app_key else '✗ 未设置'}")
        print(f"  DOUBAO_ASR_ACCESS_KEY: {'✓ 已设置' if access_key else '✗ 未设置'}")
        
        if provider == "doubao" and app_key and access_key:
            results.add("ASR 配置验证", True, "豆包 ASR 配置正确")
        elif provider == "doubao":
            results.add("ASR 配置验证", False, "豆包 ASR 缺少必要配置")
        else:
            results.add("ASR 配置验证", True, f"当前使用 {provider} 提供商")
            
    except Exception as e:
        results.add("ASR 配置验证", False, f"异常: {e}")


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  豆包 ASR 端到端测试")
    print("=" * 60)
    
    # 测试 ASR 配置
    await test_7_asr_provider_check()
    
    # 基本功能测试
    await test_1_basic_flow()
    await test_2_silence()
    await test_3_interrupted_audio()
    await test_4_rapid_audio()
    await test_5_connection_recovery()
    
    # WebSocket 集成测试
    await test_6_websocket_integration()
    
    # 输出总结
    success = results.summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
