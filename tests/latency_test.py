#!/usr/bin/env python3
"""
服务链路延时测试脚本
测试各个服务端点的网络延时和API响应时间
"""
import asyncio
import time
import os
import sys
import httpx
import socket
from typing import Optional, Tuple
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))


class LatencyTester:
    """延时测试器"""
    
    def __init__(self):
        self.results = {}
        
    def print_header(self):
        """打印测试头部"""
        print("\n" + "=" * 80)
        print("🔍 服务链路延时测试")
        print(f"📅 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
    async def ping_tcp(self, host: str, port: int = 443, timeout: float = 5.0) -> Tuple[bool, float]:
        """TCP连接延时测试"""
        try:
            start = time.perf_counter()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            latency = (time.perf_counter() - start) * 1000  # ms
            writer.close()
            await writer.wait_closed()
            return True, latency
        except Exception as e:
            return False, -1
    
    async def test_http_latency(self, url: str, method: str = "GET", 
                                 headers: dict = None, timeout: float = 10.0) -> Tuple[bool, float, str]:
        """HTTP请求延时测试"""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                start = time.perf_counter()
                if method == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.head(url, headers=headers)
                latency = (time.perf_counter() - start) * 1000  # ms
                return True, latency, f"HTTP {response.status_code}"
        except httpx.TimeoutException:
            return False, -1, "Timeout"
        except Exception as e:
            return False, -1, str(e)[:50]
    
    async def test_api_latency(self, name: str, url: str, api_key: str = None,
                                test_type: str = "models") -> dict:
        """API服务延时测试"""
        result = {
            "name": name,
            "url": url,
            "tcp_latency_ms": -1,
            "http_latency_ms": -1,
            "api_latency_ms": -1,
            "status": "❌ 失败"
        }
        
        # 解析主机名
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        
        # 1. TCP 连接测试
        tcp_ok, tcp_latency = await self.ping_tcp(host, port)
        if tcp_ok:
            result["tcp_latency_ms"] = round(tcp_latency, 2)
        
        # 2. HTTP 请求测试 (不带认证)
        http_ok, http_latency, http_msg = await self.test_http_latency(url)
        if http_ok:
            result["http_latency_ms"] = round(http_latency, 2)
        
        # 3. API 请求测试 (带认证)
        if api_key and test_type == "models":
            try:
                headers = {"Authorization": f"Bearer {api_key}"}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    start = time.perf_counter()
                    response = await client.get(f"{url}/models", headers=headers)
                    latency = (time.perf_counter() - start) * 1000
                    result["api_latency_ms"] = round(latency, 2)
                    if response.status_code == 200:
                        result["status"] = "✅ 正常"
                    else:
                        result["status"] = f"⚠️ HTTP {response.status_code}"
            except Exception as e:
                result["api_status"] = str(e)[:30]
        elif api_key and test_type == "health":
            # Supabase 健康检查
            try:
                headers = {"apikey": api_key}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    start = time.perf_counter()
                    response = await client.get(f"{url}/rest/v1/", headers=headers)
                    latency = (time.perf_counter() - start) * 1000
                    result["api_latency_ms"] = round(latency, 2)
                    if response.status_code in [200, 401]:  # 401 也说明服务在线
                        result["status"] = "✅ 正常"
                    else:
                        result["status"] = f"⚠️ HTTP {response.status_code}"
            except Exception as e:
                pass
        else:
            if http_ok:
                result["status"] = "✅ 可达"
        
        return result
    
    async def test_minimax(self) -> dict:
        """测试 MiniMax TTS 服务"""
        api_key = os.getenv("MINIMAX_API_KEY", "")
        url = "https://api.minimax.chat/v1"
        
        result = {
            "name": "MiniMax TTS",
            "url": url,
            "tcp_latency_ms": -1,
            "http_latency_ms": -1,
            "api_latency_ms": -1,
            "status": "❌ 失败"
        }
        
        # TCP 测试
        tcp_ok, tcp_latency = await self.ping_tcp("api.minimax.chat", 443)
        if tcp_ok:
            result["tcp_latency_ms"] = round(tcp_latency, 2)
        
        # API 测试
        if api_key:
            try:
                headers = {"Authorization": f"Bearer {api_key}"}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    start = time.perf_counter()
                    # MiniMax 模型列表接口
                    response = await client.get(
                        "https://api.minimax.chat/v1/models",
                        headers=headers
                    )
                    latency = (time.perf_counter() - start) * 1000
                    result["api_latency_ms"] = round(latency, 2)
                    if response.status_code == 200:
                        result["status"] = "✅ 正常"
                    else:
                        result["status"] = f"⚠️ HTTP {response.status_code}"
            except Exception as e:
                result["status"] = f"❌ {str(e)[:30]}"
        
        return result
    
    async def test_doubao_asr(self) -> dict:
        """测试豆包 ASR (WebSocket 端点)"""
        endpoint = os.getenv("DOUBAO_ASR_ENDPOINT", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async")
        
        result = {
            "name": "豆包 ASR",
            "url": "openspeech.bytedance.com",
            "tcp_latency_ms": -1,
            "http_latency_ms": -1,
            "api_latency_ms": -1,
            "status": "❌ 失败"
        }
        
        # TCP 测试
        tcp_ok, tcp_latency = await self.ping_tcp("openspeech.bytedance.com", 443)
        if tcp_ok:
            result["tcp_latency_ms"] = round(tcp_latency, 2)
            result["status"] = "✅ 可达 (WSS)"
        
        return result
    
    async def test_deepgram(self) -> dict:
        """测试 Deepgram ASR"""
        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        
        result = {
            "name": "Deepgram ASR",
            "url": "api.deepgram.com",
            "tcp_latency_ms": -1,
            "http_latency_ms": -1,
            "api_latency_ms": -1,
            "status": "❌ 失败"
        }
        
        # TCP 测试
        tcp_ok, tcp_latency = await self.ping_tcp("api.deepgram.com", 443)
        if tcp_ok:
            result["tcp_latency_ms"] = round(tcp_latency, 2)
        
        # API 测试
        if api_key:
            try:
                headers = {"Authorization": f"Token {api_key}"}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    start = time.perf_counter()
                    response = await client.get(
                        "https://api.deepgram.com/v1/projects",
                        headers=headers
                    )
                    latency = (time.perf_counter() - start) * 1000
                    result["api_latency_ms"] = round(latency, 2)
                    if response.status_code == 200:
                        result["status"] = "✅ 正常"
                    else:
                        result["status"] = f"⚠️ HTTP {response.status_code}"
            except Exception as e:
                result["status"] = f"❌ {str(e)[:30]}"
        
        return result
    
    def print_result(self, result: dict):
        """打印单个测试结果"""
        print(f"\n┌{'─' * 60}┐")
        print(f"│ {result['name']:<58} │")
        print(f"├{'─' * 60}┤")
        print(f"│  URL: {result['url']:<52} │")
        print(f"│  TCP 连接延时:  {result['tcp_latency_ms']:>8} ms" + " " * 30 + "│")
        print(f"│  HTTP 延时:     {result['http_latency_ms']:>8} ms" + " " * 30 + "│")
        print(f"│  API 响应延时:  {result['api_latency_ms']:>8} ms" + " " * 30 + "│")
        print(f"│  状态: {result['status']:<51} │")
        print(f"└{'─' * 60}┘")
    
    async def run_all_tests(self):
        """运行所有测试"""
        self.print_header()
        
        # 获取 API Keys
        openai_key = os.getenv("OPENAI_API_KEY", "")
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        dashscope_key = os.getenv("DASHSCOPE_API_KEY", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")
        supabase_url = os.getenv("SUPABASE_URL", "")
        
        print("\n📡 测试网络连接和 API 延时...\n")
        
        # 测试 tu-zi.com (主要 LLM)
        result1 = await self.test_api_latency(
            "tu-zi.com 代理 (GPT-4o)",
            "https://api.tu-zi.com/v1",
            openai_key,
            "models"
        )
        self.print_result(result1)
        
        # 测试 OpenRouter
        result2 = await self.test_api_latency(
            "OpenRouter (备用)",
            "https://openrouter.ai/api/v1",
            openrouter_key,
            "models"
        )
        self.print_result(result2)
        
        # 测试 DashScope
        result3 = await self.test_api_latency(
            "DashScope 阿里云 (备用)",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            dashscope_key,
            "models"
        )
        self.print_result(result3)
        
        # 测试 Supabase
        if supabase_url:
            result4 = await self.test_api_latency(
                "Supabase 数据库",
                supabase_url,
                supabase_key,
                "health"
            )
            self.print_result(result4)
        
        # 测试 MiniMax TTS
        result5 = await self.test_minimax()
        self.print_result(result5)
        
        # 测试豆包 ASR
        result6 = await self.test_doubao_asr()
        self.print_result(result6)
        
        # 测试 Deepgram
        result7 = await self.test_deepgram()
        self.print_result(result7)
        
        # 汇总表格
        print("\n" + "=" * 80)
        print("📊 延时汇总")
        print("=" * 80)
        print(f"{'服务名称':<25} {'TCP(ms)':<12} {'HTTP(ms)':<12} {'API(ms)':<12} {'状态':<15}")
        print("-" * 80)
        
        all_results = [result1, result2, result3, result5, result6, result7]
        if supabase_url:
            all_results.insert(3, result4)
            
        for r in all_results:
            tcp = f"{r['tcp_latency_ms']:.1f}" if r['tcp_latency_ms'] > 0 else "N/A"
            http = f"{r['http_latency_ms']:.1f}" if r['http_latency_ms'] > 0 else "N/A"
            api = f"{r['api_latency_ms']:.1f}" if r['api_latency_ms'] > 0 else "N/A"
            print(f"{r['name']:<25} {tcp:<12} {http:<12} {api:<12} {r['status']:<15}")
        
        print("-" * 80)
        
        # 延时评估
        print("\n📝 延时分析:")
        print("-" * 60)
        
        for r in all_results:
            if r['tcp_latency_ms'] > 0:
                if r['tcp_latency_ms'] < 50:
                    level = "🟢 极低 (本地/国内)"
                elif r['tcp_latency_ms'] < 150:
                    level = "🟡 正常 (国内)"
                elif r['tcp_latency_ms'] < 300:
                    level = "🟠 较高 (跨境)"
                else:
                    level = "🔴 很高 (海外/网络差)"
                print(f"  {r['name']}: TCP {r['tcp_latency_ms']:.0f}ms - {level}")
        
        print("\n" + "=" * 80)


async def main():
    tester = LatencyTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
