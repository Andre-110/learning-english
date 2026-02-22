"""
100 轮连续对话测试

测试指标：
1. 上下文理解 - 模型是否记住之前内容
2. 对话压缩 - 历史管理是否正常
3. 连续性 - 对话是否连贯
4. 延迟 - 每轮响应时间
"""
import asyncio
import websockets
import json
import time
import random
from pathlib import Path
from collections import defaultdict
import statistics

# 测试音频文件
AUDIO_DIR = Path("/home/ubuntu/learning_english/test_audio")
AUDIO_FILES = list(AUDIO_DIR.glob("*.mp3")) + list(AUDIO_DIR.glob("*.wav"))


class ConversationTester:
    def __init__(self, uri: str):
        self.uri = uri
        self.ws = None
        self.conversation_history = []  # 记录对话内容
        self.metrics = {
            "latencies": [],           # 每轮延迟
            "response_lengths": [],     # 响应长度
            "transcriptions": [],       # 转录内容
            "responses": [],            # AI 响应
            "errors": [],               # 错误
            "evaluations": [],          # 评估结果
        }
    
    async def connect(self):
        """建立 WebSocket 连接"""
        self.ws = await websockets.connect(self.uri, ping_interval=None)
        
        # 等待初始问候
        initial_text = ""
        while True:
            msg = await asyncio.wait_for(self.ws.recv(), timeout=60)
            data = json.loads(msg)
            if data.get('type') == 'text_chunk':
                initial_text += data.get('text', '')
            elif data.get('type') == 'done':
                break
        
        self.conversation_history.append({
            "round": 0,
            "role": "assistant",
            "content": initial_text
        })
        print(f"[初始] {initial_text[:60]}...")
        return initial_text
    
    async def send_audio_and_receive(self, round_num: int) -> dict:
        """发送音频并接收响应"""
        # 随机选择一个音频文件
        audio_file = random.choice(AUDIO_FILES)
        audio_data = audio_file.read_bytes()
        audio_format = audio_file.suffix[1:]  # mp3 or wav
        
        result = {
            "round": round_num,
            "audio_file": audio_file.name,
            "transcription": "",
            "response": "",
            "evaluation": None,
            "latency": 0,
            "error": None
        }
        
        start_time = time.time()
        
        try:
            # 发送开始信号
            await self.ws.send(json.dumps({"type": "start"}))
            
            # 发送音频元数据
            await self.ws.send(json.dumps({"type": "audio_meta", "format": audio_format}))
            
            # 发送音频数据（分块）
            chunk_size = 16 * 1024
            for i in range(0, len(audio_data), chunk_size):
                await self.ws.send(audio_data[i:i + chunk_size])
            
            # 发送结束信号
            await self.ws.send(json.dumps({"type": "audio_end"}))
            
            # 接收响应
            response_text = ""
            transcription = ""
            evaluation = None
            
            while True:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=120)
                data = json.loads(msg)
                msg_type = data.get('type')
                
                if msg_type == 'text_chunk':
                    response_text += data.get('text', '')
                elif msg_type == 'transcription':
                    transcription = data.get('text', '')
                elif msg_type == 'transcription_chunk':
                    # 流式转录，累加
                    pass
                elif msg_type == 'evaluation':
                    evaluation = data.get('data', {})
                elif msg_type == 'done':
                    break
                elif msg_type == 'error':
                    result["error"] = data.get('message', 'Unknown error')
                    break
            
            result["latency"] = time.time() - start_time
            result["transcription"] = transcription
            result["response"] = response_text
            result["evaluation"] = evaluation
            
            # 记录到对话历史
            if transcription:
                self.conversation_history.append({
                    "round": round_num,
                    "role": "user",
                    "content": transcription
                })
            if response_text:
                self.conversation_history.append({
                    "round": round_num,
                    "role": "assistant",
                    "content": response_text
                })
            
        except asyncio.TimeoutError:
            result["error"] = "Timeout"
            result["latency"] = time.time() - start_time
        except Exception as e:
            result["error"] = str(e)
            result["latency"] = time.time() - start_time
        
        return result
    
    async def close(self):
        """关闭连接"""
        if self.ws:
            await self.ws.close()
    
    def get_stats(self) -> dict:
        """计算统计数据"""
        latencies = self.metrics["latencies"]
        if not latencies:
            return {}
        
        return {
            "total_rounds": len(latencies),
            "latency_avg": statistics.mean(latencies),
            "latency_min": min(latencies),
            "latency_max": max(latencies),
            "latency_p50": statistics.median(latencies),
            "latency_p95": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies),
            "latency_stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "error_count": len(self.metrics["errors"]),
            "avg_response_length": statistics.mean(self.metrics["response_lengths"]) if self.metrics["response_lengths"] else 0,
        }


async def run_test(rounds: int = 100):
    """运行 100 轮测试"""
    uri = "ws://localhost:8000/ws/openrouter-audio?user_level=A2&user_id=test_100_rounds"
    
    print("=" * 70)
    print(f"100 轮连续对话测试")
    print("=" * 70)
    
    tester = ConversationTester(uri)
    
    try:
        # 连接
        print("\n[连接中...]")
        await tester.connect()
        print("[连接成功]\n")
        
        # 进行 N 轮对话
        for i in range(1, rounds + 1):
            result = await tester.send_audio_and_receive(i)
            
            # 记录指标
            tester.metrics["latencies"].append(result["latency"])
            tester.metrics["response_lengths"].append(len(result["response"]))
            tester.metrics["transcriptions"].append(result["transcription"])
            tester.metrics["responses"].append(result["response"])
            if result["evaluation"]:
                tester.metrics["evaluations"].append(result["evaluation"])
            if result["error"]:
                tester.metrics["errors"].append({"round": i, "error": result["error"]})
            
            # 打印进度
            status = "✓" if not result["error"] else f"✗ {result['error']}"
            trans_preview = result["transcription"][:30] + "..." if len(result["transcription"]) > 30 else result["transcription"]
            resp_preview = result["response"][:40] + "..." if len(result["response"]) > 40 else result["response"]
            
            print(f"[{i:3}/{rounds}] {result['latency']:.2f}s | {status}")
            print(f"       转录: {trans_preview}")
            print(f"       回复: {resp_preview}")
            
            # 每 10 轮打印统计
            if i % 10 == 0:
                stats = tester.get_stats()
                print(f"\n--- 第 {i} 轮统计 ---")
                print(f"    平均延迟: {stats['latency_avg']:.2f}s")
                print(f"    P50/P95: {stats['latency_p50']:.2f}s / {stats['latency_p95']:.2f}s")
                print(f"    错误数: {stats['error_count']}")
                print()
            
            # 短暂延迟避免过载
            await asyncio.sleep(0.5)
        
        # 最终统计
        print("\n" + "=" * 70)
        print("最终统计")
        print("=" * 70)
        stats = tester.get_stats()
        print(f"总轮数: {stats['total_rounds']}")
        print(f"平均延迟: {stats['latency_avg']:.2f}s")
        print(f"最小延迟: {stats['latency_min']:.2f}s")
        print(f"最大延迟: {stats['latency_max']:.2f}s")
        print(f"P50 延迟: {stats['latency_p50']:.2f}s")
        print(f"P95 延迟: {stats['latency_p95']:.2f}s")
        print(f"延迟标准差: {stats['latency_stdev']:.2f}s")
        print(f"错误数: {stats['error_count']}")
        print(f"平均响应长度: {stats['avg_response_length']:.0f} 字符")
        
        # 检查上下文理解
        print("\n" + "=" * 70)
        print("上下文连续性检查")
        print("=" * 70)
        print(f"对话历史长度: {len(tester.conversation_history)} 条消息")
        
        # 打印最后 5 轮对话
        print("\n最后 5 轮对话:")
        recent = tester.conversation_history[-10:] if len(tester.conversation_history) >= 10 else tester.conversation_history
        for msg in recent:
            role = "用户" if msg["role"] == "user" else "AI"
            content = msg["content"][:60] + "..." if len(msg["content"]) > 60 else msg["content"]
            print(f"  [{msg['round']}] {role}: {content}")
        
        # 错误详情
        if tester.metrics["errors"]:
            print("\n" + "=" * 70)
            print("错误详情")
            print("=" * 70)
            for err in tester.metrics["errors"]:
                print(f"  轮 {err['round']}: {err['error']}")
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(run_test(100))

