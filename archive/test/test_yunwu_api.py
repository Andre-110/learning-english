#!/usr/bin/env python3
"""
测试yunwu.ai API代理
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv()

def test_yunwu_api():
    """测试yunwu.ai API代理"""
    print("=" * 60)
    print("测试 yunwu.ai API 代理")
    print("=" * 60)
    print()
    
    # 获取API密钥和base_url
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://yunwu.ai")
    
    if not api_key or api_key == "your_openai_api_key_here":
        print("❌ API密钥未配置")
        return False
    
    print(f"✅ API密钥: {api_key[:10]}...{api_key[-10:]}")
    print(f"✅ Base URL: {base_url}")
    print()
    
    # 确保base_url以/v1结尾
    if not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    
    # 创建OpenAI客户端（使用yunwu.ai代理）
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        print(f"✅ OpenAI客户端创建成功（使用代理: {base_url}）")
    except Exception as e:
        print(f"❌ 创建客户端失败: {e}")
        return False
    
    # 测试1: 简单文本生成
    print("\n" + "-" * 60)
    print("测试1: GPT-4-turbo 文本生成（通过yunwu.ai代理）")
    print("-" * 60)
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "user", "content": "Say 'Hello' in one word."}
            ],
            max_tokens=10
        )
        result = response.choices[0].message.content
        print(f"✅ GPT-4-turbo 调用成功")
        print(f"   响应: {result}")
    except Exception as e:
        print(f"❌ GPT-4-turbo 调用失败: {e}")
        print(f"   错误详情: {str(e)}")
        return False
    
    # 测试2: JSON格式输出
    print("\n" + "-" * 60)
    print("测试2: JSON格式输出")
    print("-" * 60)
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "user", "content": 'Return a JSON object: {"test": "success"}'}
            ],
            response_format={"type": "json_object"},
            max_tokens=20
        )
        result = response.choices[0].message.content
        print(f"✅ JSON格式输出成功")
        print(f"   响应: {result}")
    except Exception as e:
        print(f"❌ JSON格式输出失败: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！yunwu.ai代理工作正常。")
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        success = test_yunwu_api()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试中断")
        exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

