#!/usr/bin/env python3
"""
Tuzi API 测试与延迟计算脚本（单文件独立运行）

用途：测试 Tuzi（api.tu-zi.com）的 Key 是否有效，并测量请求延迟。
依赖：仅 Python 标准库，无需 pip install。

Tuzi API 说明：
- 端点为 OpenAI 兼容 REST API: https://api.tu-zi.com/v1
- Key 与 Base URL 写在脚本内（DEFAULT_API_KEY、DEFAULT_BASE_URL），也可通过环境变量覆盖

使用方法：
  1. 指定 .env 路径（可选，默认当前目录 .env）：
     python test_tuzi_api.py --env /path/to/.env

  2. 或直接设置环境变量后运行：
     export OPENAI_OFFICIAL_API_KEY=sk-xxx
     python test_tuzi_api.py

延迟计算：端到端 = 请求发出到收到完整响应的总耗时（ms）
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.request


def load_env(env_path: str) -> None:
    """从 .env 文件加载到 os.environ"""
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1]
                elif v.startswith("'") and v.endswith("'"):
                    v = v[1:-1]
                os.environ[k] = v


def run_test(env_path: str) -> int:
    load_env(env_path)

    # 优先读环境变量 / .env，否则使用下方默认值
    DEFAULT_BASE_URL = "https://api.tu-zi.com/v1"
    DEFAULT_API_KEY = "sk-go24HjU7jzefN9o8glDZ9veIdih15ilhzuG3W8DdjvGYymC2"

    base_url = (
        os.environ.get("OPENAI_OFFICIAL_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")
    api_key = (
        os.environ.get("OPENAI_OFFICIAL_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or DEFAULT_API_KEY
    )

    print("=" * 60)
    print("Tuzi API 测试与延迟计算")
    print("=" * 60)

    print("\n【1】Key 配置检查")
    print("-" * 40)
    if not api_key:
        print("  ❌ OPENAI_OFFICIAL_API_KEY / OPENAI_API_KEY 未设置")
        print("  请设置环境变量或在 --env 指定的 .env 中配置")
        return 1
    mask = api_key[:10] + "..." + api_key[-4:] if len(api_key) > 14 else "***"
    print(f"  ✓ API Key: {mask}")
    print(f"  ✓ Base URL: {base_url}")

    print("\n【2】延迟测试")
    print("-" * 40)

    url = f"{base_url}/chat/completions"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "say hi in one word"}],
        "max_tokens": 10,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    t_start = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
        t_end = time.perf_counter()
    except urllib.error.HTTPError as e:
        print(f"  ❌ HTTP 错误 {e.code}: {e.reason}")
        try:
            err_body = e.read().decode("utf-8")
            print(f"     {err_body[:200]}")
        except Exception:
            pass
        return 1
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return 1

    total_ms = (t_end - t_start) * 1000

    try:
        data = json.loads(raw)
        choices = data.get("choices", [])
        model = data.get("model", "N/A")
        content = ""
        if choices and choices[0].get("message"):
            content = (choices[0]["message"].get("content") or "").strip()
    except json.JSONDecodeError:
        model = "N/A"
        content = raw[:80]

    user_msg = payload["messages"][0]["content"]
    print(f"  输入: {user_msg}")
    print(f"  输出: {content}")
    print(f"  延迟: {total_ms:.0f} ms")

    print("\n【3】结论")
    print("-" * 40)
    print("  ✓ Tuzi API Key 有效，服务可用")

    print("\n" + "=" * 60)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Tuzi API Key 测试与延迟计算")
    parser.add_argument("--env", default=".env", help=".env 文件路径")
    args = parser.parse_args()

    env_path = args.env
    if not os.path.isabs(env_path):
        # 相对路径：优先脚本同目录，再当前工作目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(script_dir, env_path),
            os.path.join(os.getcwd(), env_path),
        ]
        for p in candidates:
            if os.path.isfile(p):
                env_path = p
                break
        else:
            env_path = os.path.join(os.getcwd(), env_path)

    return run_test(env_path)


if __name__ == "__main__":
    sys.exit(main())
