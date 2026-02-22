#!/usr/bin/env python3
"""
端到端延时测试 - 模拟真实 API 调用
"""
import asyncio
import time
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

import httpx


async def test_llm_chat(name: str, base_url: str, api_key: str, model: str):
    """测试 LLM 聊天响应延时"""
    print(f"\n🔄 测试 {name} ({model})...")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Say 'Hello' in one word only."}
        ],
        "max_tokens": 10,
        "temperature": 0
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            start = time.perf_counter()
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            latency = (time.perf_counter() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"   ✅ 响应延时: {latency:.0f}ms")
                print(f"   📝 响应内容: {content[:50]}")
                return latency
            else:
                print(f"   ❌ HTTP {response.status_code}: {response.text[:100]}")
                return -1
    except Exception as e:
        print(f"   ❌ 错误: {str(e)[:80]}")
        return -1


async def main():
    print("\n" + "=" * 70)
    print("🚀 端到端 LLM API 延时测试")
    print(f"📅 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    results = {}
    
    # 1. tu-zi.com 代理 (GPT-4o)
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        lat = await test_llm_chat(
            "tu-zi.com 代理",
            "https://api.tu-zi.com/v1",
            openai_key,
            "gpt-4o"
        )
        results["tu-zi.com (GPT-4o)"] = lat
    
    # 2. DashScope (阿里云)
    dashscope_key = os.getenv("DASHSCOPE_API_KEY", "")
    if dashscope_key:
        lat = await test_llm_chat(
            "DashScope 阿里云",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            dashscope_key,
            "qwen-turbo"
        )
        results["DashScope (qwen-turbo)"] = lat
    
    # 3. OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_key:
        lat = await test_llm_chat(
            "OpenRouter",
            "https://openrouter.ai/api/v1",
            openrouter_key,
            "openai/gpt-4o-mini"
        )
        results["OpenRouter (GPT-4o-mini)"] = lat
    
    # 汇总
    print("\n" + "=" * 70)
    print("📊 LLM API 端到端延时对比")
    print("=" * 70)
    print(f"{'服务':<35} {'延时(ms)':<15} {'评估':<20}")
    print("-" * 70)
    
    for name, lat in results.items():
        if lat > 0:
            if lat < 500:
                level = "🟢 极快"
            elif lat < 1000:
                level = "🟡 正常"
            elif lat < 2000:
                level = "🟠 较慢"
            else:
                level = "🔴 很慢"
            print(f"{name:<35} {lat:<15.0f} {level:<20}")
        else:
            print(f"{name:<35} {'失败':<15} {'❌ 不可用':<20}")
    
    print("-" * 70)
    
    # 架构分析
    print("\n" + "=" * 70)
    print("🔍 服务架构延时分析")
    print("=" * 70)
    print("""
┌─────────────────────────────────────────────────────────────────────┐
│                        服务位置与延时分析                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   用户 → 北京阿里云ECS(47.93.101.73:8000) → 各服务                    │
│                                                                     │
│   ┌──────────────────┬──────────────┬────────────────────────────┐  │
│   │ 服务             │ 位置         │ 延时评估                    │  │
│   ├──────────────────┼──────────────┼────────────────────────────┤  │
│   │ tu-zi.com        │ 海外代理     │ 🔴 高延时 (跨境)             │  │
│   │ OpenRouter       │ 美国         │ 🟠 较高 (跨境)               │  │
│   │ Deepgram         │ 美国         │ 🔴 高延时 (跨境)             │  │
│   │ Supabase         │ 海外         │ 🔴 高延时 (跨境)             │  │
│   ├──────────────────┼──────────────┼────────────────────────────┤  │
│   │ DashScope        │ 阿里云杭州   │ 🟢 极低 (国内同网)           │  │
│   │ 豆包 ASR         │ 字节国内     │ 🟢 极低 (国内)               │  │
│   │ MiniMax TTS      │ 国内         │ 🟢 低 (国内)                │  │
│   └──────────────────┴──────────────┴────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

📋 建议:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 🔴 高延时瓶颈: tu-zi.com 代理 (TCP 354ms, API ~700ms+)
   - 这是海外代理，跨境通信延时不可避免
   - 建议: 考虑切换到 DashScope (qwen) 作为主力 LLM

2. 🟢 低延时优势: 
   - DashScope 阿里云: TCP 8ms, API 67ms - 同在阿里云，极低延时
   - 豆包 ASR: TCP 25ms - 国内字节跳动服务
   - MiniMax TTS: TCP 33ms - 国内服务

3. 🔴 Supabase 数据库延时高 (TCP 398ms, API 2000ms+)
   - 海外数据库，每次数据操作都有高延时
   - 建议: 考虑迁移到阿里云 RDS/PolarDB
   
4. ⚡ 优化建议:
   - 将 LLM 从 tu-zi.com 切换到 DashScope (延时降低 10x)
   - 当前 ASR (豆包) + TTS (MiniMax) 已是国内低延时
   - 数据库可考虑国内方案减少延时
""")


if __name__ == "__main__":
    asyncio.run(main())
