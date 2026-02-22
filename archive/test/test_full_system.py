#!/usr/bin/env python3
"""
完整系统测试 - 测试所有核心功能
"""
import requests
import json
import time
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

def print_section(title, char="="):
    print("\n" + char * 70)
    print(f" {title}")
    print(char * 70)

def test_health_check():
    """测试1: 健康检查"""
    print_section("测试1: 健康检查")
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        assert response.status_code == 200
        data = response.json()
        print(f"✅ 服务状态: {data['status']}")
        print(f"   版本: {data['version']}")
        return True
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return False

def test_start_conversation():
    """测试2: 开始对话"""
    print_section("测试2: 开始对话")
    try:
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json={"user_id": "test_full_001"},
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✅ 对话已开始")
        print(f"   对话ID: {data['conversation_id']}")
        print(f"   初始问题: {data['initial_question'][:100]}...")
        return data["conversation_id"]
    except Exception as e:
        print(f"❌ 开始对话失败: {e}")
        return None

def test_multiple_rounds(conversation_id: str):
    """测试3: 多轮对话"""
    print_section("测试3: 多轮对话测试")
    
    test_cases = [
        {
            "input": "I am a student. 我喜欢读书。",
            "description": "中英文混杂回答"
        },
        {
            "input": "I think reading books can help us learn new vocabulary and improve our grammar skills.",
            "description": "纯英文回答，表达观点"
        },
        {
            "input": "Yes, I read every day. 我每天读30分钟。It helps me relax.",
            "description": "中英文混合，包含具体信息"
        },
    ]
    
    results = []
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- 第{i}轮对话 ---")
        print(f"输入类型: {case['description']}")
        print(f"用户输入: {case['input']}")
        
        try:
            response = requests.post(
                f"{BASE_URL}/conversations/{conversation_id}/respond",
                json={"user_response": case['input']},
                timeout=60
            )
            assert response.status_code == 200
            data = response.json()
            
            assessment = data['assessment']
            profile = assessment['ability_profile']
            
            print(f"✅ 处理成功")
            print(f"   评估分数: {profile['overall_score']:.1f}/100")
            print(f"   CEFR等级: {profile['cefr_level']}")
            print(f"   强项: {', '.join(profile['strengths']) if profile['strengths'] else '无'}")
            print(f"   弱项: {', '.join(profile['weaknesses']) if profile['weaknesses'] else '无'}")
            
            # 显示维度评分
            print(f"   维度评分:")
            for dim in assessment['dimension_scores']:
                print(f"     - {dim['dimension']}: {dim['score']:.1f}/5")
            
            print(f"   下一题: {data['next_question'][:80]}...")
            
            results.append({
                "round": i,
                "score": profile['overall_score'],
                "level": profile['cefr_level'],
                "strengths": profile['strengths'],
                "weaknesses": profile['weaknesses']
            })
            
            time.sleep(1)
        except Exception as e:
            print(f"❌ 第{i}轮失败: {e}")
            import traceback
            traceback.print_exc()
    
    return results

def test_ability_progression(results: list):
    """测试4: 能力进步轨迹"""
    print_section("测试4: 能力进步轨迹分析")
    
    if len(results) < 2:
        print("⚠️  轮次不足，无法分析进步轨迹")
        return
    
    print("能力变化:")
    for i, result in enumerate(results, 1):
        print(f"  第{i}轮: {result['score']:.1f}分, {result['level']}级")
    
    # 分析趋势
    scores = [r['score'] for r in results]
    if len(scores) > 1:
        trend = "上升" if scores[-1] > scores[0] else "下降" if scores[-1] < scores[0] else "稳定"
        print(f"\n趋势: {trend}")
        print(f"  起始分数: {scores[0]:.1f}")
        print(f"  最终分数: {scores[-1]:.1f}")
        print(f"  变化: {scores[-1] - scores[0]:+.1f}")

def test_conversation_info(conversation_id: str):
    """测试5: 获取对话信息"""
    print_section("测试5: 获取对话信息")
    try:
        response = requests.get(f"{BASE_URL}/conversations/{conversation_id}", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        print(f"✅ 对话信息获取成功")
        print(f"   对话ID: {data['conversation_id']}")
        print(f"   用户ID: {data['user_id']}")
        print(f"   状态: {data['state']}")
        print(f"   总轮数: {data['round_count']}")
        if data.get('current_question'):
            print(f"   当前问题: {data['current_question'][:80]}...")
        return True
    except Exception as e:
        print(f"❌ 获取对话信息失败: {e}")
        return False

def test_adaptation_logic(results: list):
    """测试6: 自适应逻辑"""
    print_section("测试6: 难度自适应逻辑")
    
    if len(results) < 2:
        print("⚠️  轮次不足，无法测试自适应逻辑")
        return
    
    print("难度调整分析:")
    for i in range(len(results) - 1):
        prev = results[i]
        curr = results[i + 1]
        
        prev_level = prev['level']
        curr_level = curr['level']
        prev_score = prev['score']
        curr_score = curr['score']
        
        if curr_level != prev_level:
            change = "提升" if curr_level > prev_level else "降低"
            print(f"  第{i+1}轮 → 第{i+2}轮: {prev_level} → {curr_level} ({change})")
            print(f"    分数变化: {prev_score:.1f} → {curr_score:.1f}")
        else:
            print(f"  第{i+1}轮 → 第{i+2}轮: 保持 {curr_level} 级")
            print(f"    分数变化: {prev_score:.1f} → {curr_score:.1f}")

def test_mixed_language():
    """测试7: 中英文混杂处理"""
    print_section("测试7: 中英文混杂处理")
    
    conversation_id = test_start_conversation()
    if not conversation_id:
        return
    
    mixed_inputs = [
        "I am a student. 我喜欢读书。",
        "Reading is good. 阅读可以开阔视野。",
        "I read every day. 我每天读30分钟。It helps me learn.",
    ]
    
    print("\n测试中英文混杂回答:")
    for i, input_text in enumerate(mixed_inputs, 1):
        print(f"\n第{i}轮: {input_text}")
        try:
            response = requests.post(
                f"{BASE_URL}/conversations/{conversation_id}/respond",
                json={"user_response": input_text},
                timeout=60
            )
            if response.status_code == 200:
                data = response.json()
                assessment = data['assessment']
                
                # 检查评估中是否包含中英文混合的评估
                for dim in assessment['dimension_scores']:
                    if '中英文' in dim['comment'] or '混合' in dim['comment']:
                        print(f"  ✅ 系统识别并评估了中英文混杂")
                        print(f"     评语: {dim['comment']}")
                        break
                
                print(f"  评估分数: {assessment['ability_profile']['overall_score']:.1f}/100")
            time.sleep(1)
        except Exception as e:
            print(f"  ❌ 失败: {e}")

def generate_test_report(results: list):
    """生成测试报告"""
    print_section("测试报告总结", "=")
    
    print("\n📊 测试统计:")
    print(f"   总测试轮数: {len(results)}")
    if results:
        avg_score = sum(r['score'] for r in results) / len(results)
        print(f"   平均分数: {avg_score:.1f}/100")
        
        levels = [r['level'] for r in results]
        final_level = levels[-1] if levels else "N/A"
        print(f"   最终CEFR等级: {final_level}")
        
        # 强项和弱项统计
        all_strengths = []
        all_weaknesses = []
        for r in results:
            all_strengths.extend(r['strengths'])
            all_weaknesses.extend(r['weaknesses'])
        
        if all_strengths:
            from collections import Counter
            strength_counts = Counter(all_strengths)
            print(f"\n   常见强项: {', '.join([s for s, _ in strength_counts.most_common(3)])}")
        
        if all_weaknesses:
            weakness_counts = Counter(all_weaknesses)
            print(f"   常见弱项: {', '.join([w for w, _ in weakness_counts.most_common(3)])}")
    
    print("\n✅ 系统功能测试完成！")

def main():
    """主测试流程"""
    print("=" * 70)
    print(" LinguaCoach 完整系统测试")
    print("=" * 70)
    
    # 1. 健康检查
    if not test_health_check():
        print("\n❌ 服务未运行，请先启动服务")
        return
    
    # 2. 开始对话
    conversation_id = test_start_conversation()
    if not conversation_id:
        return
    
    # 3. 多轮对话测试
    results = test_multiple_rounds(conversation_id)
    
    # 4. 能力进步轨迹
    if results:
        test_ability_progression(results)
    
    # 5. 获取对话信息
    test_conversation_info(conversation_id)
    
    # 6. 自适应逻辑测试
    if results:
        test_adaptation_logic(results)
    
    # 7. 中英文混杂处理测试
    test_mixed_language()
    
    # 8. 生成测试报告
    if results:
        generate_test_report(results)
    
    print("\n" + "=" * 70)
    print(" 所有测试完成！")
    print("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n测试中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()





