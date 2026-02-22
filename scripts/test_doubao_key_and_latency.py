#!/usr/bin/env python3
"""
豆包 ASR Key 测试与延迟计算脚本

用途：独立测试 DOUBAO_ASR 相关 Key 是否有效，并测量端到端延迟。

当前使用的 Key 说明：
- 项目使用 豆包（Doubao）流式 ASR，对应环境变量：
  - DOUBAO_ASR_APP_KEY
  - DOUBAO_ASR_ACCESS_KEY
  - DOUBAO_ASR_SECRET_KEY
- 若你指的是「tuzi」或其他 Key，请说明对应服务，本脚本仅覆盖豆包 ASR。

使用方法：
  1. 在项目根目录执行：
     cd /home/ecs-user/learning_english
     python scripts/test_doubao_key_and_latency.py

  2. 或指定 .env 路径：
     python scripts/test_doubao_key_and_latency.py --env .env

  3. 可选参数：
     --env PATH       .env 文件路径（默认 .env）
     --duration N     发送的测试音频时长（秒，默认 2）
     --verbose        打印详细日志

延迟计算说明：
  - 连接延迟：建立 WebSocket 到收到首包的时间
  - 首包延迟（TTFB）：发送首块音频到收到第一个转录结果的时间
  - 端到端延迟：发送完整音频到收到最终转录的时间
"""

import argparse
import asyncio
import math
import os
import struct
import sys
import time

# 添加项目根目录与 services
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services"))

from dotenv import load_dotenv

# 解析参数
parser = argparse.ArgumentParser(
    description="豆包 ASR Key 测试与延迟计算",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=__doc__,
)
parser.add_argument("--env", default=".env", help=".env 文件路径")
parser.add_argument("--duration", type=float, default=2.0, help="测试音频时长（秒）")
parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
args = parser.parse_args()

# 加载环境变量
env_path = os.path.join(ROOT, args.env) if not os.path.isabs(args.env) else args.env
load_dotenv(env_path)


def generate_speech_like_audio(duration_sec: float, sample_rate: int = 16000) -> bytes:
    """生成类语音 PCM（16kHz, 16bit mono）"""
    num_samples = int(sample_rate * duration_sec)
    samples = []
    freqs = [200, 400, 800, 1200]
    for i in range(num_samples):
        t = i / sample_rate
        value = 0
        for freq in freqs:
            mod = 1 + 0.3 * math.sin(2 * math.pi * 3 * t)
            value += 0.2 * mod * math.sin(2 * math.pi * freq * t)
        value = int(32767 * value)
        value = max(-32768, min(32767, value))
        samples.append(struct.pack("<h", value))
    return b"".join(samples)


async def run_test():
    from services.doubao_asr import DoubaoASR, DoubaoASRConfig

    app_key = os.getenv("DOUBAO_ASR_APP_KEY", "")
    access_key = os.getenv("DOUBAO_ASR_ACCESS_KEY", "")
    secret_key = os.getenv("DOUBAO_ASR_SECRET_KEY", "")

    print("=" * 60)
    print("豆包 ASR Key 测试与延迟计算")
    print("=" * 60)

    # 1. 检查 Key 是否配置
    print("\n【1】Key 配置检查")
    print("-" * 40)
    ok = True
    if not app_key:
        print("  ❌ DOUBAO_ASR_APP_KEY 未设置")
        ok = False
    else:
        mask = app_key[:8] + "..." + app_key[-4:] if len(app_key) > 12 else "***"
        print(f"  ✓ DOUBAO_ASR_APP_KEY: {mask}")

    if not access_key:
        print("  ❌ DOUBAO_ASR_ACCESS_KEY 未设置")
        ok = False
    else:
        mask = access_key[:8] + "..." + access_key[-4:] if len(access_key) > 12 else "***"
        print(f"  ✓ DOUBAO_ASR_ACCESS_KEY: {mask}")

    if not secret_key:
        print("  ❌ DOUBAO_ASR_SECRET_KEY 未设置")
        ok = False
    else:
        mask = secret_key[:8] + "..." + secret_key[-4:] if len(secret_key) > 12 else "***"
        print(f"  ✓ DOUBAO_ASR_SECRET_KEY: {mask}")

    if not ok:
        print("\n请在 .env 中配置上述变量后重试。")
        return 1

    # 2. 连接测试与延迟测量
    print("\n【2】连接与延迟测试")
    print("-" * 40)

    config = DoubaoASRConfig()
    asr = DoubaoASR(config=config)

    first_result_time = None
    final_result = [None]  # 用 list 便于在闭包中修改
    connection_time = None

    def on_transcript(text: str, is_final: bool):
        nonlocal first_result_time, final_result
        if first_result_time is None:
            first_result_time = time.perf_counter()
        if is_final and text.strip():
            final_result[0] = text
        if args.verbose:
            print(f"    [{'Final' if is_final else 'Interim'}] {text[:60]}...")

    t_start = time.perf_counter()
    try:
        connected = await asr.start_stream(on_transcript=on_transcript)
        connection_time = (time.perf_counter() - t_start) * 1000

        if not connected:
            print("  ❌ WebSocket 连接失败")
            return 1

        print(f"  ✓ 连接成功，耗时: {connection_time:.0f} ms")

        # 3. 发送测试音频
        chunk_size = 1600  # 100ms @ 16kHz 16bit
        audio = generate_speech_like_audio(args.duration)
        send_start = time.perf_counter()
        for i in range(0, len(audio), chunk_size):
            chunk = audio[i : i + chunk_size]
            if chunk:
                await asr.send_audio(chunk)
            await asyncio.sleep(0.05)

        send_end = time.perf_counter()
        t_send = (send_end - send_start) * 1000
        print(f"  ✓ 已发送 {len(audio)/3200:.1f} 秒音频，耗时: {t_send:.0f} ms")

        # 4. 结束流并等待最终结果
        t_stop = time.perf_counter()
        result = await asr.stop_stream()
        t_stop_end = time.perf_counter()
        stop_duration = (t_stop_end - t_stop) * 1000

        # 5. 延迟汇总
        print("\n【3】延迟统计")
        print("-" * 40)

        ttfb_ms = None
        if first_result_time is not None:
            ttfb_ms = (first_result_time - send_start) * 1000
            print(f"  首包延迟 (TTFB):     {ttfb_ms:.0f} ms")
        else:
            print("  首包延迟 (TTFB):     未收到转录（可能服务异常或音频格式不符）")

        print(f"  连接延迟:            {connection_time:.0f} ms")
        print(f"  stop_stream 等待:    {stop_duration:.0f} ms")

        total_ms = (t_stop_end - t_start) * 1000
        print(f"  端到端总耗时:        {total_ms:.0f} ms")

        # 6. 结果摘要
        print("\n【4】结论")
        print("-" * 40)
        if final_result[0] or result:
            text = (final_result[0] or result or "").strip()
            print(f"  ✓ Key 有效，服务可用")
            if text:
                print(f"  转录结果: {text[:80]}{'...' if len(text) > 80 else ''}")
        else:
            print("  ⚠ 未收到有效转录，可能原因：")
            print("    - 测试音频为模拟波形，非真实语音，豆包可能返回空")
            print("    - 网络或服务端异常")
            print("  建议：用真实语音文件测试 test_doubao_asr_e2e.py")

        print("\n" + "=" * 60)
        return 0

    except Exception as e:
        print(f"  ❌ 异常: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def main():
    return asyncio.run(run_test())


if __name__ == "__main__":
    sys.exit(main())
