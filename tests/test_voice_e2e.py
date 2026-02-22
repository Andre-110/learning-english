"""
端到端语音测试脚本

测试方式：
1. 使用 TTS 合成测试音频（带停顿）
2. 通过 WebSocket 发送音频帧
3. 收集 ASR 转录和 AI 响应
4. 验证行为是否符合预期

测试用例来源：维度二、三的测试用例
"""
import asyncio
import websockets
import json
import base64
import struct
import time
import io
from datetime import datetime
from typing import Optional, List, Tuple
from dataclasses import dataclass

# 测试服务器配置
WS_URL = "ws://localhost:8000/ws/gpt4o-pipeline"
# WS_URL = "ws://localhost:8000/ws/gpt4o-pipeline?user_id=test_user"


@dataclass
class TestResult:
    """测试结果"""
    case_id: str
    case_name: str
    audio_duration: float
    asr_text: str
    ai_response: str
    latency_ms: float
    passed: bool
    notes: str = ""


class VoiceE2ETester:
    """语音端到端测试器"""
    
    def __init__(self, ws_url: str = WS_URL):
        self.ws_url = ws_url
        self.results: List[TestResult] = []
    
    async def run_test_case(
        self, 
        case_id: str,
        case_name: str,
        audio_data: bytes,
        expected_keywords: List[str],
        should_not_interrupt: bool = True
    ) -> TestResult:
        """
        运行单个测试用例
        
        Args:
            case_id: 用例ID
            case_name: 用例名称
            audio_data: PCM 音频数据 (16kHz, 16-bit, mono)
            expected_keywords: 预期 ASR 转录应包含的关键词
            should_not_interrupt: AI 是否不应该打断（True=不应打断）
        """
        asr_texts = []
        ai_responses = []
        interrupted = False
        start_time = time.time()
        
        try:
            async with websockets.connect(self.ws_url) as ws:
                # 等待连接确认
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                print(f"  连接: {data.get('type')}")
                
                # 发送 start 消息
                await ws.send(json.dumps({"type": "start"}))
                
                # 分帧发送音频（每帧 20ms = 320 samples = 640 bytes）
                frame_size = 640  # 20ms @ 16kHz, 16-bit
                total_frames = len(audio_data) // frame_size
                
                print(f"  发送音频: {len(audio_data)} bytes, {total_frames} 帧")
                
                for i in range(total_frames):
                    frame = audio_data[i * frame_size : (i + 1) * frame_size]
                    # 转换为 Int16 数组
                    samples = list(struct.unpack(f'{len(frame)//2}h', frame))
                    
                    await ws.send(json.dumps({
                        "type": "audio_frame",
                        "data": samples
                    }))
                    
                    # 检查是否有响应（非阻塞）
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.01)
                        data = json.loads(msg)
                        
                        if data.get("type") == "asr_delta":
                            asr_texts.append(data.get("text", ""))
                            print(f"  ASR: {data.get('text', '')[:50]}...")
                        elif data.get("type") == "response":
                            ai_responses.append(data.get("text", ""))
                            interrupted = True  # AI 在用户说话时响应了
                            print(f"  ⚠️ AI 响应（可能打断）: {data.get('text', '')[:30]}...")
                    except asyncio.TimeoutError:
                        pass
                    
                    await asyncio.sleep(0.02)  # 20ms 间隔
                
                # 发送 stop_audio
                await ws.send(json.dumps({"type": "stop_audio"}))
                print("  发送 stop_audio")
                
                # 等待 AI 响应
                deadline = time.time() + 10  # 10秒超时
                while time.time() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        data = json.loads(msg)
                        
                        if data.get("type") == "asr_delta":
                            asr_texts.append(data.get("text", ""))
                        elif data.get("type") == "transcription":
                            asr_texts.append(data.get("text", ""))
                            print(f"  最终转录: {data.get('text', '')}")
                        elif data.get("type") == "response":
                            ai_responses.append(data.get("text", ""))
                            print(f"  AI 响应: {data.get('text', '')[:50]}...")
                        elif data.get("type") == "audio_end":
                            print("  音频播放完成")
                            break
                    except asyncio.TimeoutError:
                        if ai_responses:
                            break
                
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            return TestResult(
                case_id=case_id,
                case_name=case_name,
                audio_duration=len(audio_data) / 32000,  # seconds
                asr_text="",
                ai_response="",
                latency_ms=0,
                passed=False,
                notes=f"Error: {e}"
            )
        
        latency = (time.time() - start_time) * 1000
        
        # 验证结果
        final_asr = asr_texts[-1] if asr_texts else ""
        final_response = ai_responses[-1] if ai_responses else ""
        
        # 检查关键词
        keywords_found = all(kw.lower() in final_asr.lower() for kw in expected_keywords)
        
        # 检查是否打断
        interrupt_check = not interrupted if should_not_interrupt else True
        
        passed = keywords_found and interrupt_check
        
        notes = []
        if not keywords_found:
            notes.append(f"缺少关键词: {expected_keywords}")
        if should_not_interrupt and interrupted:
            notes.append("AI 不应打断但打断了")
        
        result = TestResult(
            case_id=case_id,
            case_name=case_name,
            audio_duration=len(audio_data) / 32000,
            asr_text=final_asr,
            ai_response=final_response[:100],
            latency_ms=latency,
            passed=passed,
            notes="; ".join(notes) if notes else "OK"
        )
        
        self.results.append(result)
        return result
    
    def generate_test_audio_with_pause(
        self, 
        text_segments: List[Tuple[str, float]],
        sample_rate: int = 16000
    ) -> bytes:
        """
        生成带停顿的测试音频
        
        Args:
            text_segments: [(文本, 停顿秒数), ...]
            sample_rate: 采样率
        
        Returns:
            PCM 音频数据
        """
        # 这里需要 TTS 服务，暂时生成静音占位
        # 实际测试时应该用 OpenAI TTS 或其他 TTS 生成
        
        total_duration = sum(pause for _, pause in text_segments)
        total_samples = int(total_duration * sample_rate)
        
        # 生成静音（实际应该是 TTS 生成的语音）
        silence = b'\x00\x00' * total_samples
        
        print(f"  ⚠️ 使用占位音频（静音）: {total_duration}s")
        return silence
    
    def print_summary(self):
        """打印测试汇总"""
        print("\n" + "=" * 80)
        print("📊 测试汇总")
        print("=" * 80)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        for r in self.results:
            status = "✅" if r.passed else "❌"
            print(f"{status} [{r.case_id}] {r.case_name}")
            print(f"    ASR: {r.asr_text[:50]}..." if r.asr_text else "    ASR: (空)")
            print(f"    延迟: {r.latency_ms:.0f}ms, 备注: {r.notes}")
        
        print(f"\n总计: {passed}/{total} 通过")


async def main():
    """运行语音端到端测试"""
    print("=" * 80)
    print("🎤 语音端到端测试")
    print("=" * 80)
    print("\n⚠️ 注意：此测试需要预录制的测试音频文件")
    print("当前使用占位音频（静音），仅验证 WebSocket 流程\n")
    
    tester = VoiceE2ETester()
    
    # 测试用例（需要真实音频文件）
    # 目前使用占位测试，验证流程是否正常
    
    print("\n[测试1] WebSocket 连接测试")
    print("-" * 40)
    
    try:
        async with websockets.connect(WS_URL) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            if data.get("type") == "connected":
                print("✅ WebSocket 连接成功")
                print(f"   初始问题: {data.get('initial_question', 'N/A')[:50]}...")
            else:
                print(f"❌ 意外响应: {data}")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return
    
    print("\n[测试2] Deepgram ASR 流程测试")
    print("-" * 40)
    print("需要真实音频文件，跳过...")
    
    print("\n" + "=" * 80)
    print("📋 如何进行完整测试：")
    print("=" * 80)
    print("""
1. 录制测试音频文件（16kHz, 16-bit, mono PCM）
   - 使用 Audacity 或其他工具录制
   - 包含停顿、语气词等测试场景

2. 将音频文件放入 tests/audio/ 目录

3. 修改此脚本，加载真实音频文件：
   ```python
   with open("tests/audio/test1_pause.pcm", "rb") as f:
       audio_data = f.read()
   await tester.run_test_case("1", "长停顿测试", audio_data, ["happy"])
   ```

4. 或者使用前端界面手动测试，按照测试用例脚本说话

5. 查看 F12 控制台和后端日志验证行为
""")


if __name__ == "__main__":
    asyncio.run(main())

