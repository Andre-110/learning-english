"""
端到端延迟测试脚本
测试从用户输入到系统响应的完整流程
"""
import asyncio
import time
import json
import base64
import websockets
import requests

# 配置
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

async def test_full_flow():
    """测试完整对话流程的延迟"""
    print("=" * 60)
    print("LinguaCoach 端到端延迟测试")
    print("=" * 60)
    
    timings = {}
    
    # 1. 创建对话
    print("\n[1] 创建对话...")
    start = time.time()
    response = requests.post(
        f"{BASE_URL}/conversations/start",
        json={"user_id": "test_latency_user"}
    )
    timings['create_conversation'] = time.time() - start
    
    if response.status_code != 200:
        print(f"创建对话失败: {response.text}")
        return
    
    data = response.json()
    conversation_id = data['conversation_id']
    initial_question = data['initial_question']
    print(f"  对话ID: {conversation_id}")
    print(f"  初始问题: {initial_question[:80]}...")
    print(f"  耗时: {timings['create_conversation']:.2f}秒")
    
    # 2. 连接 WebSocket
    print("\n[2] 连接 WebSocket...")
    ws_url = f"{WS_URL}/streaming-voice/{conversation_id}/chat"
    
    try:
        async with websockets.connect(ws_url) as ws:
            # 等待连接确认
            start = time.time()
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            timings['ws_connect'] = time.time() - start
            print(f"  连接成功: {json.loads(msg)}")
            print(f"  耗时: {timings['ws_connect']:.2f}秒")
            
            # 3. 发送音频
            print("\n[3] 发送测试音频...")
            
            # 读取测试音频
            with open('/home/ubuntu/learning_english/test_audio/test_simple.mp3', 'rb') as f:
                audio_data = f.read()
            
            # 发送开始标记
            await ws.send(json.dumps({"type": "start"}))
            
            # 发送音频数据
            start = time.time()
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            await ws.send(json.dumps({
                "type": "audio_data",
                "data": audio_base64
            }))
            
            # 发送结束标记
            await ws.send(json.dumps({"type": "audio_end"}))
            timings['send_audio'] = time.time() - start
            print(f"  音频大小: {len(audio_data)} bytes")
            print(f"  发送耗时: {timings['send_audio']:.2f}秒")
            
            # 4. 接收响应
            print("\n[4] 等待响应...")
            start = time.time()
            first_response_time = None
            transcription_time = None
            question_time = None
            tts_start_time = None
            tts_end_time = None
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=120)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    elapsed = time.time() - start
                    
                    if first_response_time is None:
                        first_response_time = elapsed
                        timings['first_response'] = elapsed
                    
                    if msg_type == 'transcription_final':
                        transcription_time = elapsed
                        timings['transcription'] = elapsed
                        print(f"  转录完成 ({elapsed:.2f}s): {data.get('text', '')[:50]}...")
                    
                    elif msg_type == 'assessment':
                        timings['assessment'] = elapsed
                        assessment = data.get('data', {}).get('assessment', {})
                        print(f"  评估完成 ({elapsed:.2f}s): 分数={assessment.get('overall_score')}, 等级={assessment.get('cefr_level')}")
                    
                    elif msg_type == 'question':
                        question_time = elapsed
                        timings['question'] = elapsed
                        print(f"  问题生成 ({elapsed:.2f}s): {data.get('text', '')[:50]}...")
                    
                    elif msg_type == 'audio_chunk':
                        if tts_start_time is None:
                            tts_start_time = elapsed
                            timings['tts_first_chunk'] = elapsed
                            print(f"  TTS首块 ({elapsed:.2f}s)")
                    
                    elif msg_type == 'audio_end':
                        tts_end_time = elapsed
                        timings['tts_complete'] = elapsed
                        stats = data.get('stats', {})
                        print(f"  TTS完成 ({elapsed:.2f}s): {stats.get('chunks')}块, {stats.get('total_bytes')}字节")
                        break
                    
                    elif msg_type == 'processing':
                        stage = data.get('stage', '')
                        print(f"  处理中 ({elapsed:.2f}s): {data.get('message', stage)}")
                    
                    elif msg_type == 'error':
                        print(f"  错误: {data.get('message')}")
                        break
                    
                except asyncio.TimeoutError:
                    print("  超时！")
                    break
            
            # 5. 总结
            print("\n" + "=" * 60)
            print("延迟分析总结")
            print("=" * 60)
            
            print(f"\n创建对话:     {timings.get('create_conversation', 0):.2f}秒")
            print(f"WebSocket连接: {timings.get('ws_connect', 0):.2f}秒")
            print(f"发送音频:     {timings.get('send_audio', 0):.2f}秒")
            print(f"首次响应:     {timings.get('first_response', 0):.2f}秒")
            print(f"转录完成:     {timings.get('transcription', 0):.2f}秒")
            print(f"评估完成:     {timings.get('assessment', 0):.2f}秒")
            print(f"问题生成:     {timings.get('question', 0):.2f}秒")
            print(f"TTS首块:      {timings.get('tts_first_chunk', 0):.2f}秒")
            print(f"TTS完成:      {timings.get('tts_complete', 0):.2f}秒")
            
            total = timings.get('tts_complete', 0)
            print(f"\n总延迟:       {total:.2f}秒")
            
            if total < 5:
                print("\n✅ 性能优秀！")
            elif total < 10:
                print("\n⚠️ 性能良好，可进一步优化")
            else:
                print("\n❌ 性能较慢，需要优化")
            
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_full_flow())

