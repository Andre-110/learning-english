"""
GPT-4o Audio 模式延迟测试
对比标准模式 vs GPT-4o Audio 模式
"""
import asyncio
import time
import json
import base64
import websockets
import requests

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

async def test_gpt4o_audio_mode():
    """测试 GPT-4o Audio 模式"""
    print("=" * 60)
    print("GPT-4o Audio 模式延迟测试")
    print("=" * 60)
    
    timings = {}
    
    # 1. 创建对话
    print("\n[1] 创建对话...")
    start = time.time()
    response = requests.post(
        f"{BASE_URL}/conversations/start",
        json={"user_id": "test_gpt4o_user"}
    )
    timings['create_conversation'] = time.time() - start
    
    if response.status_code != 200:
        print(f"创建对话失败: {response.text}")
        return
    
    data = response.json()
    conversation_id = data['conversation_id']
    print(f"  对话ID: {conversation_id}")
    print(f"  耗时: {timings['create_conversation']:.2f}秒")
    
    # 2. 连接 GPT-4o Audio WebSocket
    print("\n[2] 连接 GPT-4o Audio WebSocket...")
    ws_url = f"{WS_URL}/gpt4o-audio/{conversation_id}/chat"
    
    try:
        async with websockets.connect(ws_url) as ws:
            start = time.time()
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            timings['ws_connect'] = time.time() - start
            conn_data = json.loads(msg)
            print(f"  连接成功: mode={conn_data.get('mode')}")
            print(f"  耗时: {timings['ws_connect']:.2f}秒")
            
            # 3. 发送音频
            print("\n[3] 发送测试音频...")
            
            with open('/home/ubuntu/learning_english/test_audio/test_simple.mp3', 'rb') as f:
                audio_data = f.read()
            
            await ws.send(json.dumps({"type": "start"}))
            
            start = time.time()
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            await ws.send(json.dumps({
                "type": "audio_data",
                "data": audio_base64
            }))
            await ws.send(json.dumps({"type": "audio_end"}))
            timings['send_audio'] = time.time() - start
            print(f"  音频大小: {len(audio_data)} bytes")
            print(f"  发送耗时: {timings['send_audio']:.2f}秒")
            
            # 4. 接收响应
            print("\n[4] 等待响应...")
            start = time.time()
            first_chunk_time = None
            transcription_time = None
            response_time = None
            tts_start_time = None
            tts_end_time = None
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    elapsed = time.time() - start
                    
                    if msg_type == 'processing':
                        print(f"  处理中 ({elapsed:.2f}s): {data.get('message', data.get('stage'))}")
                    
                    elif msg_type == 'response_chunk':
                        if first_chunk_time is None:
                            first_chunk_time = elapsed
                            timings['first_chunk'] = elapsed
                            print(f"  首字到达 ({elapsed:.2f}s)")
                    
                    elif msg_type == 'transcription':
                        transcription_time = elapsed
                        timings['transcription'] = elapsed
                        print(f"  转录完成 ({elapsed:.2f}s): {data.get('text', '')[:50]}...")
                    
                    elif msg_type == 'evaluation':
                        timings['evaluation'] = elapsed
                        assessment = data.get('data', {}).get('assessment', {})
                        print(f"  评估完成 ({elapsed:.2f}s): 分数={assessment.get('overall_score')}")
                    
                    elif msg_type in ['response', 'response_complete']:
                        response_time = elapsed
                        timings['response'] = elapsed
                        print(f"  响应完成 ({elapsed:.2f}s): {data.get('text', '')[:50]}...")
                    
                    elif msg_type == 'audio_chunk':
                        if tts_start_time is None:
                            tts_start_time = elapsed
                            timings['tts_start'] = elapsed
                            print(f"  TTS首块 ({elapsed:.2f}s)")
                    
                    elif msg_type == 'audio_end':
                        tts_end_time = elapsed
                        timings['tts_end'] = elapsed
                        print(f"  TTS完成 ({elapsed:.2f}s)")
                        break
                    
                    elif msg_type == 'stats':
                        stats = data.get('data', {})
                        print(f"  统计: GPT-4o={stats.get('gpt4o_time_ms')}ms, 首字={stats.get('first_chunk_ms')}ms, 总计={stats.get('total_time_ms')}ms")
                    
                    elif msg_type == 'error':
                        print(f"  错误: {data.get('message')}")
                        break
                    
                except asyncio.TimeoutError:
                    print("  超时！")
                    break
            
            # 5. 总结
            print("\n" + "=" * 60)
            print("GPT-4o Audio 延迟分析")
            print("=" * 60)
            
            print(f"\n创建对话:     {timings.get('create_conversation', 0):.2f}秒")
            print(f"WebSocket连接: {timings.get('ws_connect', 0):.2f}秒")
            print(f"发送音频:     {timings.get('send_audio', 0):.2f}秒")
            print(f"首字到达:     {timings.get('first_chunk', 'N/A')}")
            print(f"转录完成:     {timings.get('transcription', 'N/A')}")
            print(f"评估完成:     {timings.get('evaluation', 'N/A')}")
            print(f"响应完成:     {timings.get('response', 'N/A')}")
            print(f"TTS首块:      {timings.get('tts_start', 'N/A')}")
            print(f"TTS完成:      {timings.get('tts_end', 'N/A')}")
            
            total = timings.get('tts_end', 0) or timings.get('response', 0)
            print(f"\n总延迟:       {total:.2f}秒")
            
            # 对比分析
            print("\n" + "-" * 40)
            print("对比分析（GPT-4o Audio vs 标准模式）")
            print("-" * 40)
            print("标准模式流程: STT(0.5s) → 快速评估(1-2s) → 问题生成(2-4s) → TTS(2-3s)")
            print("GPT-4o模式:   GPT-4o(转录+评估+生成) → TTS")
            print("\n理论优势: 减少1-2次LLM调用")
            
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gpt4o_audio_mode())

