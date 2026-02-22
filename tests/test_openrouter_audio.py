"""
测试 OpenRouter 的 GPT-4o Audio 模型
"""
import base64
import json
import os
import sys
import time
import struct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

OPENROUTER_API_KEY = "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"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def generate_test_audio_wav(duration_seconds=2, sample_rate=16000):
    """生成测试用的 WAV 音频（静音）"""
    import math
    
    num_samples = int(sample_rate * duration_seconds)
    # 生成静音或简单的正弦波
    samples = []
    for i in range(num_samples):
        # 生成一个简单的音调
        t = i / sample_rate
        sample = int(32767 * 0.3 * math.sin(2 * math.pi * 440 * t))  # 440Hz
        samples.append(sample)
    
    # 创建 WAV 文件头
    audio_data = struct.pack('<' + 'h' * len(samples), *samples)
    
    # WAV 文件格式
    wav_header = struct.pack('<4sI4s', b'RIFF', 36 + len(audio_data), b'WAVE')
    fmt_chunk = struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    data_chunk = struct.pack('<4sI', b'data', len(audio_data))
    
    return wav_header + fmt_chunk + data_chunk + audio_data


def test_gpt4o_audio_openrouter():
    """测试 OpenRouter 的 GPT-4o Audio"""
    print("=" * 60)
    print("🧪 测试 OpenRouter GPT-4o Audio")
    print("=" * 60)
    
    # 生成测试音频
    print("\n[1] 生成测试音频...")
    audio_data = generate_test_audio_wav(duration_seconds=1)
    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
    print(f"    音频大小: {len(audio_data)} bytes")
    
    # 构建请求
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://usergenie.ai",  # OpenRouter 需要
        "X-Title": "LinguaCoach"  # OpenRouter 需要
    }
    
    # 测试普通文本请求先
    print("\n[2] 测试普通文本请求...")
    text_payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Say hello in one word."}
        ],
        "max_tokens": 10
    }
    
    start_time = time.time()
    resp = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=text_payload
    )
    text_latency = time.time() - start_time
    
    if resp.status_code == 200:
        result = resp.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        print(f"    ✅ 成功! 响应: {content}")
        print(f"    延迟: {text_latency:.2f}秒")
    else:
        print(f"    ❌ 失败: {resp.status_code}")
        print(f"    {resp.text[:500]}")
        return False
    
    # 测试音频请求
    print("\n[3] 测试 GPT-4o Audio 请求...")
    audio_payload = {
        "model": "openai/gpt-4o-audio-preview",
        "messages": [
            {
                "role": "system",
                "content": "You are an English tutor. Listen to the audio and respond briefly."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_base64,
                            "format": "wav"
                        }
                    },
                    {
                        "type": "text",
                        "text": "What did you hear in this audio? Please describe briefly."
                    }
                ]
            }
        ],
        "max_tokens": 200
    }
    
    start_time = time.time()
    resp = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=audio_payload
    )
    audio_latency = time.time() - start_time
    
    if resp.status_code == 200:
        result = resp.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        print(f"    ✅ 成功!")
        print(f"    响应: {content[:200]}...")
        print(f"    延迟: {audio_latency:.2f}秒")
        
        # 显示 usage
        usage = result.get('usage', {})
        print(f"    Token 使用: prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}")
        
        return True
    else:
        print(f"    ❌ 失败: {resp.status_code}")
        print(f"    {resp.text[:500]}")
        
        # 尝试解析错误
        try:
            error = resp.json()
            print(f"    错误详情: {json.dumps(error, indent=2)}")
        except:
            pass
        
        return False


def test_realtime_models():
    """检查是否有 Realtime 相关模型"""
    print("\n" + "=" * 60)
    print("🔍 检查 Realtime 相关模型")
    print("=" * 60)
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }
    
    resp = requests.get(f"{OPENROUTER_BASE_URL}/models", headers=headers)
    if resp.status_code == 200:
        models = resp.json().get('data', [])
        
        realtime_models = [m for m in models if 'realtime' in m.get('id', '').lower()]
        
        if realtime_models:
            print("找到 Realtime 模型:")
            for m in realtime_models:
                print(f"  - {m.get('id')}")
                print(f"    描述: {m.get('description', 'N/A')[:100]}")
        else:
            print("❌ 未找到 Realtime 模型")
            print("   OpenRouter 可能不支持 WebSocket 协议的 Realtime API")
    else:
        print(f"获取模型列表失败: {resp.status_code}")


def test_streaming():
    """测试流式输出"""
    print("\n" + "=" * 60)
    print("⚡ 测试流式输出")
    print("=" * 60)
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://usergenie.ai",
        "X-Title": "LinguaCoach"
    }
    
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Count from 1 to 5, one number per line."}
        ],
        "max_tokens": 50,
        "stream": True
    }
    
    print("发送流式请求...")
    start_time = time.time()
    first_token_time = None
    
    resp = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        stream=True
    )
    
    if resp.status_code == 200:
        full_content = ""
        for line in resp.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        if delta:
                            if first_token_time is None:
                                first_token_time = time.time()
                                print(f"首 token 延迟: {first_token_time - start_time:.2f}秒")
                            full_content += delta
                            print(delta, end='', flush=True)
                    except json.JSONDecodeError:
                        pass
        
        total_time = time.time() - start_time
        print(f"\n\n✅ 流式输出完成")
        print(f"   总耗时: {total_time:.2f}秒")
    else:
        print(f"❌ 失败: {resp.status_code}")
        print(resp.text[:500])


if __name__ == "__main__":
    # 测试基本功能
    success = test_gpt4o_audio_openrouter()
    
    # 检查 Realtime 模型
    test_realtime_models()
    
    # 测试流式输出
    test_streaming()
    
    print("\n" + "=" * 60)
    print("📊 总结")
    print("=" * 60)
    if success:
        print("✅ OpenRouter GPT-4o Audio 可用!")
        print("   可以用于 Audio In → LLM → TTS 流程")
    else:
        print("⚠️ GPT-4o Audio 测试未通过")
        print("   可能需要检查模型支持或请求格式")

