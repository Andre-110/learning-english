#!/usr/bin/env python3
"""
终端调用云驿 Claude（使用 ~/.claude/settings.json 配置）

用法:
  python3 claude_terminal.py "你好"
  python3 claude_terminal.py   # 交互模式，输入多行后空行发送
  python3 claude_terminal.py -   # 从标准输入读一整段

依赖: 仅标准库 (json, urllib)
"""
import json
import os
import sys
import urllib.request
import ssl

CONFIG_PATH = os.path.expanduser("~/.claude/settings.json")
DEFAULT_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_VERSION = "2023-06-01"


def load_config():
    if not os.path.isfile(CONFIG_PATH):
        print("未找到配置，请先运行: npx yunyi-activator", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    env = data.get("env") or {}
    base = (env.get("ANTHROPIC_BASE_URL") or "").rstrip("/")
    token = env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or ""
    if not base or not token:
        print("配置中缺少 ANTHROPIC_BASE_URL 或 ANTHROPIC_AUTH_TOKEN", file=sys.stderr)
        sys.exit(1)
    return base, token


def chat(base_url: str, api_key: str, user_message: str, model: str = DEFAULT_MODEL) -> str:
    url = f"{base_url}/v1/messages"
    body = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": user_message}],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    # 解析 content
    for block in out.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


def main():
    base, token = load_config()
    model = DEFAULT_MODEL

    if len(sys.argv) > 1:
        if sys.argv[1] == "-":
            user_message = sys.stdin.read().strip()
        else:
            user_message = " ".join(sys.argv[1:])
    else:
        print("交互模式，输入内容后空行发送，Ctrl+C 退出")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "":
                break
            lines.append(line)
        user_message = "\n".join(lines)

    if not user_message.strip():
        print("未输入内容")
        sys.exit(0)

    try:
        reply = chat(base, token, user_message, model)
        print(reply)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"API 错误 {e.code}: {err_body[:500]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"请求失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
