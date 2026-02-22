"""
连贯对话流程测试

使用现有测试音频，测试：
1. AI 响应质量（是否避免 "You said..." 模式）
2. 延迟趋势（随对话增长是否增加）
3. 上下文记忆（多轮后是否保持连贯）
"""
import asyncio
import websockets
import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# 测试音频文件
AUDIO_DIR = Path("/home/ubuntu/learning_english/test_audio")
# 按顺序使用这些音频（循环）
AUDIO_FILES = [
    AUDIO_DIR / "test_simple.mp3",    # I am a student, I like reading books
    AUDIO_DIR / "en_simple.mp3",       # 简单句子
    AUDIO_DIR / "test_medium.mp3",     # 中等难度
    AUDIO_DIR / "en_medium.mp3",       # 中等难度
    AUDIO_DIR / "en_travel.mp3",       # 旅行话题
]


class ConversationTester:
    def __init__(self, uri: str):
        self.uri = uri
        self.ws = None
        self.history = []
        self.metrics = {
            "latencies": [],
            "banned_pattern_violations": [],
            "responses": [],
        }
    
    async def connect(self):
        """建立连接"""
        self.ws = await websockets.connect(self.uri, ping_interval=None)
        
        initial_text = ""
        while True:
            msg = await asyncio.wait_for(self.ws.recv(), timeout=60)
            data = json.loads(msg)
            if data.get('type') == 'text_chunk':
                initial_text += data.get('text', '')
            elif data.get('type') == 'done':
                break
        
        self.history.append({"role": "assistant", "content": initial_text})
        return initial_text
    
    async def send_audio(self, audio_path: Path, round_num: int) -> dict:
        """发送音频并接收响应"""
        result = {
            "round": round_num,
            "audio_file": audio_path.name,
            "transcription": "",
            "response": "",
            "latency": 0,
            "banned_pattern": False,
            "error": None
        }
        
        audio_data = audio_path.read_bytes()
        audio_format = audio_path.suffix[1:]
        
        start_time = time.time()
        
        try:
            # 发送音频
            await self.ws.send(json.dumps({"type": "start"}))
            await self.ws.send(json.dumps({"type": "audio_meta", "format": audio_format}))
            
            chunk_size = 16 * 1024
            for i in range(0, len(audio_data), chunk_size):
                await self.ws.send(audio_data[i:i + chunk_size])
            
            await self.ws.send(json.dumps({"type": "audio_end"}))
            
            # 接收响应
            response_text = ""
            transcription = ""
            got_processing = False
            
            while True:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=120)
                data = json.loads(msg)
                msg_type = data.get('type')
                
                if msg_type == 'processing':
                    got_processing = True
                elif msg_type == 'text_chunk':
                    response_text += data.get('text', '')
                elif msg_type == 'transcription':
                    transcription = data.get('text', '')
                elif msg_type == 'done':
                    if got_processing:
                        break
                elif msg_type == 'error':
                    result["error"] = data.get('message')
                    break
            
            result["latency"] = time.time() - start_time
            result["transcription"] = transcription
            result["response"] = response_text
            
            # 检查禁止模式
            banned_starts = ["You said", "You mentioned", "That's great!", "That's interesting!"]
            for pattern in banned_starts:
                if response_text.strip().startswith(pattern):
                    result["banned_pattern"] = True
                    self.metrics["banned_pattern_violations"].append({
                        "round": round_num,
                        "pattern": pattern,
                        "response": response_text[:60]
                    })
                    break
            
            # 记录历史
            self.history.append({"role": "user", "content": transcription})
            self.history.append({"role": "assistant", "content": response_text})
            
        except Exception as e:
            result["error"] = str(e)
            result["latency"] = time.time() - start_time
        
        return result
    
    async def close(self):
        if self.ws:
            await self.ws.close()


async def run_test(rounds: int = 20):
    """运行对话测试"""
    uri = "ws://localhost:8000/ws/openrouter-audio?user_level=A2&user_id=test_flow"
    
    print("=" * 70)
    print(f"{rounds} 轮连续对话测试")
    print("=" * 70)
    
    tester = ConversationTester(uri)
    
    try:
        # 连接
        print("\n[连接中...]")
        initial = await tester.connect()
        print(f"[初始] {initial[:60]}...")
        print()
        
        # 执行对话
        for i in range(1, rounds + 1):
            # 循环使用音频文件
            audio_file = AUDIO_FILES[(i - 1) % len(AUDIO_FILES)]
            result = await tester.send_audio(audio_file, i)
            
            tester.metrics["latencies"].append(result["latency"])
            tester.metrics["responses"].append(result["response"])
            
            # 打印结果
            status = "✗ BANNED" if result["banned_pattern"] else "✓"
            if result["error"]:
                status = f"✗ {result['error'][:20]}"
            
            print(f"[{i:2}] {result['latency']:.2f}s {status} | {result['audio_file']}")
            print(f"     转录: {result['transcription'][:50]}...")
            print(f"     AI: {result['response'][:50]}...")
            print()
            
            await asyncio.sleep(0.5)
        
        # 统计
        print("=" * 70)
        print("测试结果")
        print("=" * 70)
        
        latencies = tester.metrics["latencies"]
        print(f"\n延迟统计:")
        print(f"  平均: {sum(latencies)/len(latencies):.2f}s")
        print(f"  最小: {min(latencies):.2f}s")
        print(f"  最大: {max(latencies):.2f}s")
        
        # 延迟趋势
        first_half = latencies[:len(latencies)//2]
        second_half = latencies[len(latencies)//2:]
        print(f"  前半平均: {sum(first_half)/len(first_half):.2f}s")
        print(f"  后半平均: {sum(second_half)/len(second_half):.2f}s")
        
        # 禁止模式违规
        violations = tester.metrics["banned_pattern_violations"]
        print(f"\n禁止模式违规: {len(violations)}/{rounds}")
        for v in violations[:5]:
            print(f"  轮 {v['round']}: \"{v['pattern']}...\" -> {v['response'][:40]}")
        
        # 响应多样性
        unique_starts = set()
        for resp in tester.metrics["responses"]:
            if resp:
                # 取前 3 个词作为开头
                words = resp.split()[:3]
                unique_starts.add(" ".join(words))
        print(f"\n响应开头多样性: {len(unique_starts)} 种不同开头")
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(run_test(100))
