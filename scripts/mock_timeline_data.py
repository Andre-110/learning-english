import requests
import json
import time
import random
from datetime import datetime, timezone

# 目标地址
API_BASE = "http://localhost:8000"
TIMELINE_URL = f"{API_BASE}/api/logs/timeline"

def send_event(user_id, conversation_id, round_id, event_type, offset_ms, message_round_id):
    """发送单个时间轴事件"""
    # 当前时间 - 偏移量（模拟过去发生的事情）
    # 但为了方便，我们假设 base_time 是过去某个点，offset 是相对于 base 的增量
    pass

def simulate_round(user_id, conversation_id, round_id, scenario_name, delays):
    """模拟一轮对话"""
    print(f"🚀 模拟场景 [{scenario_name}] - 轮次 #{round_id}")
    
    message_round_id = f"{conversation_id}_{round_id}"
    base_time = int(time.time() * 1000) - 60000 + (round_id * 5000) # 都在过去1分钟内
    
    # 按照时序生成事件
    # 1. client_speech_start (0)
    # 2. client_speech_end (speech_duration)
    # 3. server_audio_last (speech_duration + network_up)
    # 4. asr_start (server_audio_last)
    # 5. asr_end (asr_start + asr_cost)
    # 6. semantic_start (asr_end)
    # 7. semantic_end (semantic_start + semantic_cost)
    # 8. llm_start (semantic_end)
    # 9. llm_first_token (llm_start + llm_ttft)
    # 10. tts_first_chunk (llm_first_token + tts_prep)
    # 11. client_audio_first (tts_first_chunk + network_down)
    
    d = delays
    
    t1 = base_time
    t2 = t1 + d['speech_duration']
    t3 = t2 + d['network_up']
    t4 = t3 # asr_start
    t5 = t4 + d['asr_cost']
    t6 = t5 # semantic_start
    t7 = t6 + d['semantic_cost']
    t8 = t7 # llm_start
    t9 = t8 + d['llm_ttft']
    t10 = t9 + d['tts_prep'] # tts_first
    t11 = t10 + d['network_down'] # client_audio_first
    t12 = t11 + 2000 # tts_end (假设播放2秒)
    t13 = t12 # client_audio_end
    
    events = [
        ("client_speech_start", t1, "client"),
        ("client_speech_end", t2, "client"),
        ("server_audio_last", t3, "server"),
        ("asr_start", t4, "server"),
        ("asr_end", t5, "server"),
        ("semantic_start", t6, "server"),
        ("semantic_end", t7, "server"),
        ("llm_start", t8, "server"),
        ("llm_first_token", t9, "server"),
        ("tts_first_chunk", t10, "server"),
        ("tts_end", t12, "server"),
        ("client_audio_first", t11, "client"),
        ("client_audio_end", t13, "client"),
    ]
    
    # 批量发送（这里模拟逐个发送或后端接收到的顺序）
    for etype, ts, src in events:
        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "round_id": round_id,
            "event_type": etype,
            "timestamp_ms": ts,
            "source": src,
            "message_round_id": message_round_id,
            "metadata": {"scenario": scenario_name}
        }
        try:
            requests.post(TIMELINE_URL, json=payload)
        except Exception as e:
            print(f"发送失败: {e}")
            
    print(f"✅ 完成: {scenario_name}")

if __name__ == "__main__":
    user_id = "mock_user_001"
    conv_id = f"conv_mock_{int(time.time())}"
    
    # 定义场景 (单位 ms)
    scenarios = [
        {
            "name": "正常对话 (丝滑)",
            "delays": {
                "speech_duration": 2000, "network_up": 50, "asr_cost": 300, 
                "semantic_cost": 50, "llm_ttft": 400, "tts_prep": 200, "network_down": 50
            }
        },
        {
            "name": "网络延迟高",
            "delays": {
                "speech_duration": 2000, "network_up": 500, "asr_cost": 300, 
                "semantic_cost": 50, "llm_ttft": 400, "tts_prep": 200, "network_down": 500
            }
        },
        {
            "name": "LLM 思考久",
            "delays": {
                "speech_duration": 2000, "network_up": 50, "asr_cost": 300, 
                "semantic_cost": 50, "llm_ttft": 2500, "tts_prep": 200, "network_down": 50
            }
        },
        {
            "name": "ASR 识别慢",
            "delays": {
                "speech_duration": 5000, "network_up": 50, "asr_cost": 1500, 
                "semantic_cost": 50, "llm_ttft": 400, "tts_prep": 200, "network_down": 50
            }
        },
        {
            "name": "语义检测卡顿",
            "delays": {
                "speech_duration": 2000, "network_up": 50, "asr_cost": 300, 
                "semantic_cost": 800, "llm_ttft": 400, "tts_prep": 200, "network_down": 50
            }
        }
    ]
    
    print("⏳ 开始生成模拟数据...")
    for i, scen in enumerate(scenarios):
        simulate_round(user_id, conv_id, i + 1, scen["name"], scen["delays"])
        time.sleep(0.1)
        
    print("\n🎉 模拟完成！请去 Monitor 页面查看效果。")
