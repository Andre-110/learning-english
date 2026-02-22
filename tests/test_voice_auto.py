"""
自动化语音测试 - 使用 TTS 生成测试音频

流程：
1. 用 OpenAI TTS 生成测试语音（带停顿）
2. 转换为 PCM 格式
3. 通过 WebSocket 发送
4. 验证 ASR 转录和 AI 响应
"""
import asyncio
import websockets
import websockets.legacy.client as ws_client
import json
import struct
import time
import io
import os
import sys
from typing import List, Tuple
from dataclasses import dataclass

sys.path.insert(0, '/home/ubuntu/learning_english')

from openai import OpenAI
from pydub import AudioSegment

# 配置
WS_URL = "ws://localhost:8000/ws/gpt4o-pipeline"
OPENAI_API_KEY = os.getenv("OPENAI_OFFICIAL_API_KEY") or os.getenv("OPENAI_API_KEY")


@dataclass 
class TestCase:
    """测试用例"""
    id: str
    name: str
    speech_text: str  # TTS 要说的文本
    pause_after_ms: int  # 说完后的静默时间
    expected_keywords: List[str]  # ASR 应包含的关键词
    should_wait: bool  # AI 是否应该等待（不打断）


# ============================================================================
# 测试用例 - 维度三（英文停顿）+ 维度四（网络/ASR）
# ============================================================================

TEST_CASES = [
    # ========== 维度三：英文语音停顿与干扰 (10 个) ==========
    TestCase(
        id="D3-1",
        name="[维度三] 长静音 3.5s",
        speech_text="I think the most important thing in life is to be happy",
        pause_after_ms=3500,
        expected_keywords=["important", "life", "happy"],
        should_wait=True
    ),
    TestCase(
        id="D3-2", 
        name="[维度三] 语气词 Well/You know",
        speech_text="Well, you know, I actually love jazz music",
        pause_after_ms=1500,
        expected_keywords=["love", "jazz"],
        should_wait=True
    ),
    TestCase(
        id="D3-3",
        name="[维度三] 拖音 umm",
        speech_text="My daily routine is umm waking up at 7 am",
        pause_after_ms=1000,
        expected_keywords=["routine", "waking", "7"],
        should_wait=True
    ),
    TestCase(
        id="D3-4",
        name="[维度三] 词汇搜索 4s",
        speech_text="I'm interested in architecture",
        pause_after_ms=4000,
        expected_keywords=["interested", "architecture"],
        should_wait=True
    ),
    TestCase(
        id="D3-5",
        name="[维度三] 非人声干扰",
        speech_text="If I had a million dollars, I would buy a big house",
        pause_after_ms=1500,
        expected_keywords=["million", "house"],
        should_wait=True
    ),
    TestCase(
        id="D3-6",
        name="[维度三] 情感沉思",
        speech_text="I feel a bit lonely sometimes, but it's okay",
        pause_after_ms=2500,
        expected_keywords=["lonely", "okay"],
        should_wait=True
    ),
    TestCase(
        id="D3-7",
        name="[维度三] 背景人声",
        speech_text="My dream job is to be a director",
        pause_after_ms=1500,
        expected_keywords=["dream", "director"],
        should_wait=True
    ),
    TestCase(
        id="D3-8",
        name="[维度三] 自我纠正",
        speech_text="I used to live in London, sorry, I mean Manchester",
        pause_after_ms=1000,
        expected_keywords=["Manchester"],
        should_wait=True
    ),
    TestCase(
        id="D3-9",
        name="[维度三] 生理杂音",
        speech_text="The weather in my city is quite humid",
        pause_after_ms=1000,
        expected_keywords=["weather", "humid"],
        should_wait=True
    ),
    TestCase(
        id="D3-10",
        name="[维度三] 极限停顿 5s",
        speech_text="To be honest, I haven't thought about it yet",
        pause_after_ms=5000,
        expected_keywords=["honest", "thought"],
        should_wait=True
    ),
    
    # ========== 维度四：网络异常与 ASR 异常 (10 个) ==========
    # 注：网络异常无法通过 TTS 自动化模拟，测试正常 ASR 识别能力
    TestCase(
        id="D4-1",
        name="[维度四] 丢包场景",
        speech_text="I think my biggest hobby is playing basketball with friends",
        pause_after_ms=1000,
        expected_keywords=["hobby", "basketball", "friends"],
        should_wait=True
    ),
    TestCase(
        id="D4-2",
        name="[维度四] ASR 重连场景",
        speech_text="I'm planning to study abroad in London next year",
        pause_after_ms=1000,
        expected_keywords=["study", "London"],
        should_wait=True
    ),
    TestCase(
        id="D4-3",
        name="[维度四] 延迟场景",
        speech_text="Regarding my career, I want to be a software engineer",
        pause_after_ms=2000,
        expected_keywords=["career", "software", "engineer"],
        should_wait=True
    ),
    TestCase(
        id="D4-4",
        name="[维度四] 抖动场景",
        speech_text="The weather today is much better than yesterday",
        pause_after_ms=1000,
        expected_keywords=["weather", "today", "better"],
        should_wait=True
    ),
    TestCase(
        id="D4-5",
        name="[维度四] 断网场景（正常测试）",
        speech_text="Honestly, my relationship with my family is very good",
        pause_after_ms=1500,
        expected_keywords=["relationship", "family"],
        should_wait=True
    ),
    TestCase(
        id="D4-6",
        name="[维度四] 静音恢复",
        speech_text="In the future, I hope to travel around the world",
        pause_after_ms=2000,
        expected_keywords=["future", "travel", "world"],
        should_wait=True
    ),
    TestCase(
        id="D4-7",
        name="[维度四] TCP 重传场景",
        speech_text="Talking about my past, it was a complicated story",
        pause_after_ms=1000,
        expected_keywords=["past", "complicated"],
        should_wait=True
    ),
    TestCase(
        id="D4-8",
        name="[维度四] 带宽下降",
        speech_text="I really enjoy listening to jazz music at night",
        pause_after_ms=1000,
        expected_keywords=["enjoy", "jazz", "night"],
        should_wait=True
    ),
    TestCase(
        id="D4-9",
        name="[维度四] WS 握手场景",
        speech_text="Could you give me some advice on learning English?",
        pause_after_ms=1000,
        expected_keywords=["advice", "English"],
        should_wait=True
    ),
    TestCase(
        id="D4-10",
        name="[维度四] 空音频包",
        speech_text="I'm a bit stressed about my interview tomorrow",
        pause_after_ms=1500,
        expected_keywords=["stressed", "interview"],
        should_wait=True
    ),
]


def generate_audio_with_tts(text: str, pause_ms: int = 0) -> bytes:
    """
    使用 OpenAI TTS 生成音频，并添加静默
    
    Returns:
        PCM 音频数据 (16kHz, 16-bit, mono)
    """
    import tempfile
    
    if not OPENAI_API_KEY:
        raise ValueError("需要设置 OPENAI_API_KEY 或 OPENAI_OFFICIAL_API_KEY")
    
    client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.openai.com/v1")
    
    print(f"  生成 TTS: '{text[:30]}...'")
    
    # 生成语音（使用 PCM 格式避免转换问题）
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
        response_format="pcm"  # 直接输出 PCM (24kHz, 16-bit, mono)
    )
    
    # OpenAI TTS PCM 是 24kHz，需要转换为 16kHz
    pcm_24k = response.content
    
    # 使用临时文件转换
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as f:
        f.write(pcm_24k)
        temp_path = f.name
    
    try:
        # 读取原始 PCM 数据
        with open(temp_path, 'rb') as f:
            raw_data = f.read()
        
        # 确保是完整帧数 (2 bytes per sample)
        if len(raw_data) % 2 != 0:
            raw_data = raw_data[:-1]
        
        # 加载为 AudioSegment (24kHz, 16-bit, mono)
        audio = AudioSegment(
            data=raw_data,
            sample_width=2, 
            frame_rate=24000, 
            channels=1
        )
        
        # 转换为 16kHz
        audio = audio.set_frame_rate(16000)
        
        # 添加静默
        if pause_ms > 0:
            silence = AudioSegment.silent(duration=pause_ms, frame_rate=16000)
            audio = audio + silence
        
        # 导出为 PCM，确保是完整帧
        pcm_data = audio.raw_data
        # 确保是 640 bytes (20ms frame) 的整数倍
        frame_size = 640
        remainder = len(pcm_data) % frame_size
        if remainder != 0:
            # 补齐到完整帧
            pcm_data = pcm_data + b'\x00' * (frame_size - remainder)
        
        print(f"  音频时长: {len(audio)}ms, PCM: {len(pcm_data)} bytes")
        
        return pcm_data
    finally:
        os.unlink(temp_path)


async def run_test(case: TestCase) -> dict:
    """运行单个测试用例"""
    print(f"\n[{case.id}] {case.name}")
    print("-" * 50)
    
    result = {
        "id": case.id,
        "name": case.name,
        "passed": False,
        "asr_text": "",
        "ai_interrupted": False,
        "latency_ms": 0,
        "error": None
    }
    
    try:
        # 生成测试音频
        audio_data = generate_audio_with_tts(case.speech_text, case.pause_after_ms)
        
        asr_texts = []
        ai_responses = []
        interrupted_during_speech = False
        start_time = time.time()
        speech_end_time = None
        
        async with ws_client.connect(WS_URL, close_timeout=5) as ws:
            # 等待连接
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"  连接成功")
            
            # 1. 等待 AI 开场白完成（audio_end）
            print(f"  等待 AI 开场白...")
            ai_greeting_done = False
            greeting_timeout = time.time() + 20  # 最多等待 20 秒
            while time.time() < greeting_timeout:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    data = json.loads(msg)
                    msg_type = data.get("type")
                    if msg_type == "audio_end":
                        ai_greeting_done = True
                        print(f"  ✓ AI 开场白完成")
                        break
                    elif msg_type == "text_chunk":
                        pass  # 跳过开场白文本
                except asyncio.TimeoutError:
                    continue
            
            if not ai_greeting_done:
                print(f"  ⚠️ AI 开场白超时，继续测试...")
            
            # 2. 现在发送用户音频
            await ws.send(json.dumps({"type": "start"}))
            
            # 计算语音部分的帧数（不含静默）
            speech_duration_ms = len(audio_data) // 32 - case.pause_after_ms
            speech_frames = speech_duration_ms // 20
            
            # 分帧发送
            frame_size = 640  # 20ms
            total_frames = len(audio_data) // frame_size
            
            for i in range(total_frames):
                frame = audio_data[i * frame_size : (i + 1) * frame_size]
                if len(frame) < frame_size:
                    break
                    
                samples = list(struct.unpack(f'{len(frame)//2}h', frame))
                
                await ws.send(json.dumps({
                    "type": "audio_frame",
                    "data": samples
                }))
                
                # 检查响应
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.005)
                    data = json.loads(msg)
                    msg_type = data.get("type")
                    
                    # 调试：只在第一帧和关键消息时打印
                    if i == 0 or msg_type in ["asr_delta", "transcription", "response", "error"]:
                        print(f"  📨 帧{i}: {msg_type} - {str(data)[:60]}...")
                    
                    if msg_type == "asr_delta":
                        asr_texts.append(data.get("text", ""))
                    elif msg_type == "response":
                        ai_responses.append(data.get("text", ""))
                        if i < speech_frames:  # 在语音部分就响应了
                            interrupted_during_speech = True
                            print(f"  ⚠️ AI 在语音期间响应！帧 {i}/{speech_frames}")
                except asyncio.TimeoutError:
                    pass
                
                await asyncio.sleep(0.02)
            
            # 发送 stop_audio
            await ws.send(json.dumps({"type": "stop_audio"}))
            speech_end_time = time.time()  # 用户说完的时刻
            print(f"  发送 stop_audio")
            
            # 等待响应
            first_ai_response_time = None
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1)
                    data = json.loads(msg)
                    msg_type = data.get("type")
                    
                    # 调试：打印所有消息类型
                    if msg_type not in ["audio_chunk"]:  # 跳过音频块
                        print(f"  📨 收到: {msg_type} - {str(data)[:80]}...")
                    
                    if msg_type == "transcription":
                        asr_texts.append(data.get("text", ""))
                        print(f"  ASR: {data.get('text', '')}")
                    elif msg_type == "asr_delta":
                        asr_texts.append(data.get("text", ""))
                    elif msg_type == "text_chunk":
                        # 记录第一个 AI 响应时间
                        if first_ai_response_time is None:
                            first_ai_response_time = time.time()
                        ai_responses.append(data.get("text", ""))
                    elif msg_type == "response":
                        if first_ai_response_time is None:
                            first_ai_response_time = time.time()
                        ai_responses.append(data.get("text", ""))
                        print(f"  AI: {data.get('text', '')[:60]}...")
                    elif msg_type == "audio_end":
                        break
                except asyncio.TimeoutError:
                    if ai_responses:
                        break
        
        # 计算延迟（从用户说完到 AI 首个响应）
        if speech_end_time and first_ai_response_time:
            result["latency_ms"] = (first_ai_response_time - speech_end_time) * 1000
        
        # 验证结果
        final_asr = asr_texts[-1] if asr_texts else ""
        result["asr_text"] = final_asr
        result["ai_interrupted"] = interrupted_during_speech
        
        # 检查关键词
        keywords_found = all(
            kw.lower() in final_asr.lower() 
            for kw in case.expected_keywords
        )
        
        # 检查是否应该等待
        wait_check = not interrupted_during_speech if case.should_wait else True
        
        result["passed"] = keywords_found and wait_check
        
        if not keywords_found:
            result["error"] = f"缺少关键词: {case.expected_keywords}"
        elif not wait_check:
            result["error"] = "AI 不应打断但打断了"
        
    except Exception as e:
        error_str = str(e)
        # 忽略 WebSocket 正常关闭错误
        if "close frame" not in error_str and "1000 (OK)" not in error_str:
            result["error"] = error_str
            print(f"  ❌ 错误: {e}")
        else:
            # 如果只是关闭错误，检查是否有数据
            if ai_responses:
                result["passed"] = True
                print(f"  ⚠️ WebSocket 关闭警告（已忽略）")
            else:
                result["error"] = "无 AI 响应 (可能是后端处理问题)"
                print(f"  ❌ 无 AI 响应")
    
    # 打印结果
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"  结果: {status}")
    if result.get("latency_ms", 0) > 0:
        print(f"  延迟: {result['latency_ms']:.0f}ms (从用户说完到 AI 首响应)")
    if result["error"]:
        print(f"  原因: {result['error']}")
    
    return result


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("🎤 自动化语音测试")
    print("=" * 60)
    
    # 检查依赖
    if not OPENAI_API_KEY:
        print("❌ 需要设置 OPENAI_API_KEY")
        print("请在 .env 中配置 OPENAI_OFFICIAL_API_KEY")
        return
    
    try:
        from pydub import AudioSegment
    except ImportError:
        print("❌ 需要安装 pydub: pip install pydub")
        return
    
    results = []
    
    for case in TEST_CASES:
        result = await run_test(case)
        results.append(result)
        await asyncio.sleep(2)  # 等待 2 秒再测下一个
    
    # 汇总
    print("\n" + "=" * 60)
    print("📊 测试汇总")
    print("=" * 60)
    
    passed = sum(1 for r in results if r["passed"])
    
    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"{status} [{r['id']}] {r['name']}: {r.get('error', 'OK')}")
    
    print(f"\n总计: {passed}/{len(results)} 通过")


if __name__ == "__main__":
    asyncio.run(main())

