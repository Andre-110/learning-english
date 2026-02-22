#!/usr/bin/env python3
"""
完整测试流程 - 记录所有输入输出到日志文件
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
import time
from datetime import datetime
from services.utils.logger import create_test_logger, log_user_interaction, log_module_io

# 创建测试日志器
logger = create_test_logger("full_flow", log_dir="logs")

BASE_URL = "http://localhost:8000"

def print_section(title, char="="):
    msg = f"\n{char * 70}\n {title}\n{char * 70}"
    print(msg)
    logger.info(msg)

def test_full_flow():
    """完整测试流程"""
    logger.info("=" * 70)
    logger.info("开始完整测试流程")
    logger.info("=" * 70)
    
    print_section("完整测试流程 - 记录所有输入输出")
    
    # 测试用例
    test_cases = [
        {
            "round": 1,
            "user_input": "I am a student. 我喜欢读书。",
            "description": "中英文混杂回答"
        },
        {
            "round": 2,
            "user_input": "I am a student. I like reading books very much. Reading helps me learn new words and improve my English skills. I read for about 30 minutes every day.",
            "description": "纯英文回答，表达观点"
        },
        {
            "round": 3,
            "user_input": "Yes, I read every day. 我每天读30分钟。It helps me relax and learn new things.",
            "description": "中英文混合，包含具体信息"
        }
    ]
    
    # 1. 开始对话
    print_section("步骤1: 开始对话")
    logger.info("[TEST_STEP] 1. Starting conversation")
    
    try:
        request_data = {"user_id": "test_logging_001"}
        logger.info(f"[API_REQUEST] POST {BASE_URL}/conversations/start")
        log_module_io(logger, "API", "start_conversation", {"request": request_data})
        
        response = requests.post(
            f"{BASE_URL}/conversations/start",
            json=request_data,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        conversation_id = data["conversation_id"]
        
        log_module_io(logger, "API", "start_conversation", 
                     {"request": request_data},
                     {"response": data})
        
        logger.info(f"[API_RESPONSE] Conversation started: {conversation_id}")
        print(f"✅ 对话已开始: {conversation_id}")
        print(f"   初始问题: {data['initial_question'][:100]}...")
        
        # 记录用户交互
        log_user_interaction(
            logger,
            conversation_id=conversation_id,
            user_id="test_logging_001",
            user_input="[SYSTEM_START]",
            system_output={
                "action": "start_conversation",
                "conversation_id": conversation_id,
                "initial_question": data["initial_question"]
            }
        )
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to start conversation: {e}")
        print(f"❌ 开始对话失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return
    
    # 2. 多轮对话
    print_section("步骤2: 多轮对话测试")
    
    results = []
    for i, case in enumerate(test_cases, 1):
        print_section(f"第{case['round']}轮对话: {case['description']}")
        logger.info(f"[TEST_STEP] Round {case['round']}: {case['description']}")
        
        user_input = case["user_input"]
        print(f"用户输入: {user_input}")
        logger.info(f"[USER_INPUT] Round {case['round']}: {user_input}")
        
        try:
            request_data = {"user_response": user_input}
            logger.info(f"[API_REQUEST] POST {BASE_URL}/conversations/{conversation_id}/respond")
            log_module_io(logger, "API", "respond", 
                         {"conversation_id": conversation_id, "request": request_data})
            
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/conversations/{conversation_id}/respond",
                json=request_data,
                timeout=90
            )
            elapsed_time = time.time() - start_time
            
            assert response.status_code == 200
            data = response.json()
            
            # 记录API响应
            log_module_io(logger, "API", "respond",
                         {"conversation_id": conversation_id, "request": request_data},
                         {"response": data, "elapsed_time": f"{elapsed_time:.2f}s"})
            
            assessment = data['assessment']
            profile = assessment['ability_profile']
            
            # 记录评估结果
            logger.info(f"[ASSESSMENT_RESULT] Round {case['round']}")
            logger.info(f"  Score: {profile['overall_score']}/100")
            logger.info(f"  CEFR Level: {profile['cefr_level']}")
            logger.info(f"  Strengths: {', '.join(profile['strengths']) if profile['strengths'] else 'None'}")
            logger.info(f"  Weaknesses: {', '.join(profile['weaknesses']) if profile['weaknesses'] else 'None'}")
            
            # 记录维度评分
            logger.info(f"[DIMENSION_SCORES] Round {case['round']}")
            for dim in assessment['dimension_scores']:
                logger.info(f"  - {dim['dimension']}: {dim['score']}/5")
                logger.debug(f"    Comment: {dim.get('comment', 'N/A')}")
            
            # 记录用户交互
            log_user_interaction(
                logger,
                conversation_id=conversation_id,
                user_id="test_logging_001",
                user_input=user_input,
                system_output={
                    "round": case['round'],
                    "assessment": assessment,
                    "next_question": data.get('next_question', ''),
                    "user_profile": data.get('user_profile', {}),
                    "elapsed_time": f"{elapsed_time:.2f}s"
                }
            )
            
            print(f"✅ 处理成功 (耗时: {elapsed_time:.2f}秒)")
            print(f"   评估分数: {profile['overall_score']:.1f}/100")
            print(f"   CEFR等级: {profile['cefr_level']}")
            print(f"   强项: {', '.join(profile['strengths']) if profile['strengths'] else '无'}")
            print(f"   弱项: {', '.join(profile['weaknesses']) if profile['weaknesses'] else '无'}")
            print(f"   下一题: {data['next_question'][:80]}...")
            
            results.append({
                "round": case['round'],
                "user_input": user_input,
                "score": profile['overall_score'],
                "level": profile['cefr_level'],
                "strengths": profile['strengths'],
                "weaknesses": profile['weaknesses'],
                "elapsed_time": elapsed_time
            })
            
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"[ERROR] Round {case['round']} failed: {e}")
            print(f"❌ 第{case['round']}轮失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # 3. 获取对话信息
    print_section("步骤3: 获取对话信息")
    logger.info("[TEST_STEP] 3. Getting conversation info")
    
    try:
        logger.info(f"[API_REQUEST] GET {BASE_URL}/conversations/{conversation_id}")
        response = requests.get(f"{BASE_URL}/conversations/{conversation_id}", timeout=10)
        
        assert response.status_code == 200
        data = response.json()
        
        log_module_io(logger, "API", "get_conversation",
                     {"conversation_id": conversation_id},
                     {"response": data})
        
        logger.info(f"[CONVERSATION_INFO] Conversation ID: {data['conversation_id']}")
        logger.info(f"  User ID: {data['user_id']}")
        logger.info(f"  State: {data['state']}")
        logger.info(f"  Round Count: {data['round_count']}")
        
        print(f"✅ 对话信息获取成功")
        print(f"   对话ID: {data['conversation_id']}")
        print(f"   用户ID: {data['user_id']}")
        print(f"   状态: {data['state']}")
        print(f"   总轮数: {data['round_count']}")
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to get conversation info: {e}")
        print(f"❌ 获取对话信息失败: {e}")
    
    # 4. 结束对话
    print_section("步骤4: 结束对话")
    logger.info("[TEST_STEP] 4. Ending conversation")
    
    try:
        logger.info(f"[API_REQUEST] POST {BASE_URL}/conversations/{conversation_id}/end")
        response = requests.post(f"{BASE_URL}/conversations/{conversation_id}/end", timeout=10)
        
        assert response.status_code == 200
        data = response.json()
        
        log_module_io(logger, "API", "end_conversation",
                     {"conversation_id": conversation_id},
                     {"response": data})
        
        logger.info(f"[CONVERSATION_ENDED] Conversation {conversation_id} ended")
        print(f"✅ 对话已结束")
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to end conversation: {e}")
        print(f"❌ 结束对话失败: {e}")
    
    # 5. 测试总结
    print_section("测试总结")
    logger.info("[TEST_SUMMARY] Generating test summary")
    
    logger.info(f"[SUMMARY] Total rounds: {len(results)}")
    if results:
        avg_score = sum(r['score'] for r in results) / len(results)
        avg_time = sum(r['elapsed_time'] for r in results) / len(results)
        
        logger.info(f"[SUMMARY] Average score: {avg_score:.1f}/100")
        logger.info(f"[SUMMARY] Average response time: {avg_time:.2f}s")
        logger.info(f"[SUMMARY] Final CEFR level: {results[-1]['level']}")
        
        print(f"\n📊 测试统计:")
        print(f"   总测试轮数: {len(results)}")
        print(f"   平均分数: {avg_score:.1f}/100")
        print(f"   平均响应时间: {avg_time:.2f}秒")
        print(f"   最终CEFR等级: {results[-1]['level']}")
        
        # 记录每轮结果
        logger.info("[SUMMARY] Round-by-round results:")
        for r in results:
            logger.info(f"  Round {r['round']}: {r['score']:.1f}分, {r['level']}级, {r['elapsed_time']:.2f}s")
    
    logger.info("=" * 70)
    logger.info("测试流程完成")
    logger.info("=" * 70)
    
    print(f"\n✅ 测试完成！")
    print(f"   日志文件已保存到: logs/")

if __name__ == "__main__":
    try:
        test_full_flow()
    except KeyboardInterrupt:
        logger.warning("测试中断")
        print("\n\n测试中断")
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"\n❌ 测试失败: {e}")

