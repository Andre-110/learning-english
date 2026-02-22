#!/usr/bin/env python3
"""
API集成测试 - 测试所有API端点
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_all_endpoints():
    """测试所有API端点"""
    print("=" * 70)
    print(" API端点集成测试")
    print("=" * 70)
    
    results = {
        "passed": [],
        "failed": []
    }
    
    # 1. GET /
    print("\n1. GET / (健康检查)")
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        assert r.status_code == 200
        print(f"   ✅ 通过 - {r.json()}")
        results["passed"].append("GET /")
    except Exception as e:
        print(f"   ❌ 失败 - {e}")
        results["failed"].append("GET /")
    
    # 2. POST /conversations/start
    print("\n2. POST /conversations/start")
    conversation_id = None
    try:
        r = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "test_api_001"},
            timeout=30
        )
        assert r.status_code == 200
        data = r.json()
        conversation_id = data["conversation_id"]
        print(f"   ✅ 通过 - 对话ID: {conversation_id}")
        results["passed"].append("POST /conversations/start")
    except Exception as e:
        print(f"   ❌ 失败 - {e}")
        results["failed"].append("POST /conversations/start")
        return results
    
    # 3. POST /conversations/{id}/respond
    print("\n3. POST /conversations/{id}/respond")
    try:
        r = requests.post(
            f"{BASE_URL}/conversations/{conversation_id}/respond",
            json={"user_response": "I am a student."},
            timeout=60
        )
        assert r.status_code == 200
        data = r.json()
        assert "next_question" in data
        assert "assessment" in data
        print(f"   ✅ 通过 - 评估分数: {data['assessment']['ability_profile']['overall_score']:.1f}")
        results["passed"].append("POST /conversations/{id}/respond")
    except Exception as e:
        print(f"   ❌ 失败 - {e}")
        results["failed"].append("POST /conversations/{id}/respond")
    
    # 4. GET /conversations/{id}
    print("\n4. GET /conversations/{id}")
    try:
        r = requests.get(f"{BASE_URL}/conversations/{conversation_id}", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["conversation_id"] == conversation_id
        print(f"   ✅ 通过 - 状态: {data['state']}, 轮数: {data['round_count']}")
        results["passed"].append("GET /conversations/{id}")
    except Exception as e:
        print(f"   ❌ 失败 - {e}")
        results["failed"].append("GET /conversations/{id}")
    
    # 5. POST /conversations/{id}/end
    print("\n5. POST /conversations/{id}/end")
    try:
        r = requests.post(f"{BASE_URL}/conversations/{conversation_id}/end", timeout=10)
        assert r.status_code == 200
        print(f"   ✅ 通过 - {r.json()}")
        results["passed"].append("POST /conversations/{id}/end")
    except Exception as e:
        print(f"   ❌ 失败 - {e}")
        results["failed"].append("POST /conversations/{id}/end")
    
    # 6. GET /docs (API文档)
    print("\n6. GET /docs (API文档)")
    try:
        r = requests.get(f"{BASE_URL}/docs", timeout=5, allow_redirects=False)
        assert r.status_code in [200, 307, 308]  # 可能重定向
        print(f"   ✅ 通过 - 状态码: {r.status_code}")
        results["passed"].append("GET /docs")
    except Exception as e:
        print(f"   ❌ 失败 - {e}")
        results["failed"].append("GET /docs")
    
    return results

def print_summary(results):
    """打印测试总结"""
    print("\n" + "=" * 70)
    print(" 测试总结")
    print("=" * 70)
    print(f"\n✅ 通过: {len(results['passed'])}/{len(results['passed']) + len(results['failed'])}")
    for test in results['passed']:
        print(f"   ✅ {test}")
    
    if results['failed']:
        print(f"\n❌ 失败: {len(results['failed'])}")
        for test in results['failed']:
            print(f"   ❌ {test}")
    else:
        print("\n🎉 所有测试通过！")

if __name__ == "__main__":
    try:
        results = test_all_endpoints()
        print_summary(results)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()





