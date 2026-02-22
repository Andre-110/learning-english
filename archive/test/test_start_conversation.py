#!/usr/bin/env python3
"""
测试开始对话API
"""
import requests
import json

def test_start_conversation():
    url = "http://localhost:8000/conversations/start"
    data = {
        "user_id": "test_user_001"
    }
    
    print("测试开始对话API...")
    print(f"URL: {url}")
    print(f"Data: {json.dumps(data, indent=2)}")
    print("-" * 60)
    
    try:
        response = requests.post(url, json=data, timeout=30)
        print(f"状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print("✓ 成功!")
            print(f"响应数据: {json.dumps(result, indent=2, ensure_ascii=False)}")
        else:
            print("✗ 失败!")
            try:
                error_data = response.json()
                print(f"错误信息: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"错误文本: {response.text}")
    except requests.exceptions.ConnectionError:
        print("✗ 连接失败: 无法连接到服务器")
        print("  请确保后端服务正在运行: python -m uvicorn api.main:app --host 0.0.0.0 --port 8000")
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_start_conversation()



