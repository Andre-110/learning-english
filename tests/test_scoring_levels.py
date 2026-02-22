"""
评分规则测试 - 验证不同水平用户的评分是否对齐 CEFR 标准

测试用例设计：
- A1 (0-25): 纯中文/极简单英语
- A2 (25-45): 简单句子，有错误
- B1 (45-65): 能交流，有一些错误
- B2 (65-80): 流利，复杂句子
- C1 (80-92): 高级词汇，复杂结构
- C2 (92-100): 近母语水平
"""
import sys
import os
import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.unified_processor import create_processor, ProcessingResult, UserProfileUpdater


@dataclass
class TestUser:
    """测试用户"""
    name: str
    expected_level: str  # A1, A2, B1, B2, C1, C2
    expected_score_range: tuple  # (min, max)
    inputs: List[str]  # 用户会说的话
    description: str  # 用户描述


# 定义测试用户
TEST_USERS = [
    # ========== A1 级别 (0-25) ==========
    TestUser(
        name="小明 (A1-纯中文)",
        expected_level="A1",
        expected_score_range=(0, 25),
        inputs=[
            "我不会说英语",
            "我想学英语但是不知道怎么说",
            "请继续",
        ],
        description="完全不会英语，只说中文的初学者"
    ),
    TestUser(
        name="小红 (A1-极简单)",
        expected_level="A1",
        expected_score_range=(10, 30),
        inputs=[
            "Hello",
            "Yes, I like",
            "Good, thank you",
        ],
        description="只会最基础的单词和短语"
    ),
    
    # ========== A2 级别 (25-45) ==========
    TestUser(
        name="张三 (A2-简单句)",
        expected_level="A2",
        expected_score_range=(25, 45),
        inputs=[
            "I like play basketball.",
            "Yesterday I go to school.",
            "My mother she is teacher.",
        ],
        description="能说简单句子但有明显语法错误"
    ),
    TestUser(
        name="李四 (A2-中英混杂)",
        expected_level="A2",
        expected_score_range=(25, 45),
        inputs=[
            "I want to tell some thing about 足球 with you.",
            "I think 梅西 is very good player.",
            "Yesterday I eat 火锅, very delicious.",
        ],
        description="中英文混杂，英语部分有错误"
    ),
    
    # ========== B1 级别 (45-65) ==========
    TestUser(
        name="王五 (B1-能交流)",
        expected_level="B1",
        expected_score_range=(45, 65),
        inputs=[
            "I went to the cinema last weekend and watched a very interesting movie about time travel.",
            "I think learning English is important because it helps me communicate with people from different countries.",
            "My favorite hobby is reading books, especially science fiction novels.",
        ],
        description="能够用完整句子表达想法，偶有小错"
    ),
    TestUser(
        name="赵六 (B1-有细节)",
        expected_level="B1",
        expected_score_range=(45, 65),
        inputs=[
            "Last summer, I traveled to Beijing with my family. We visited the Great Wall and it was amazing.",
            "I usually wake up at seven o'clock and have breakfast before going to work.",
            "In my opinion, exercise is very important for health. I try to run three times a week.",
        ],
        description="能提供细节描述，句子结构较完整"
    ),
    
    # ========== B2 级别 (65-80) ==========
    TestUser(
        name="孙七 (B2-流利)",
        expected_level="B2",
        expected_score_range=(65, 80),
        inputs=[
            "Although I was initially skeptical about the movie, I found myself completely captivated by its storyline and character development.",
            "The main challenge I face when learning English is maintaining consistency, as it requires daily practice to see significant improvement.",
            "From my perspective, the rapid advancement of technology has fundamentally transformed the way we communicate and work.",
        ],
        description="流利表达，能使用复杂句式和从句"
    ),
    TestUser(
        name="周八 (B2-复杂结构)",
        expected_level="B2",
        expected_score_range=(65, 80),
        inputs=[
            "What strikes me most about this topic is how interconnected global economies have become, which makes international cooperation more essential than ever.",
            "If I had known about this opportunity earlier, I would have prepared more thoroughly for the interview.",
            "Despite the challenges we encountered during the project, our team managed to deliver the results on time.",
        ],
        description="能使用条件句、让步从句等复杂结构"
    ),
    
    # ========== C1 级别 (80-92) ==========
    TestUser(
        name="吴九 (C1-高级)",
        expected_level="C1",
        expected_score_range=(80, 92),
        inputs=[
            "The proliferation of artificial intelligence has precipitated a paradigm shift in how we conceptualize human-machine interaction, raising profound ethical considerations.",
            "Notwithstanding the considerable obstacles that impeded our progress, we persevered and ultimately achieved unprecedented results.",
            "The dichotomy between economic growth and environmental sustainability presents policymakers with an intricate dilemma that defies simplistic solutions.",
        ],
        description="高级词汇，学术表达，复杂句式"
    ),
    TestUser(
        name="郑十 (C1-精准表达)",
        expected_level="C1",
        expected_score_range=(80, 92),
        inputs=[
            "What fascinates me about linguistics is how language simultaneously shapes and reflects cultural identity, a phenomenon that becomes particularly evident in multilingual societies.",
            "The ramifications of climate change extend far beyond environmental degradation, encompassing economic instability, social displacement, and geopolitical tensions.",
            "Having devoted considerable effort to mastering this skill, I can confidently assert that consistent practice, coupled with constructive feedback, constitutes the cornerstone of proficiency.",
        ],
        description="精准用词，逻辑清晰，表达地道"
    ),
    
    # ========== C2 级别 (92-100) ==========
    TestUser(
        name="钱十一 (C2-近母语)",
        expected_level="C2",
        expected_score_range=(88, 100),
        inputs=[
            "The epistemological underpinnings of contemporary discourse on artificial consciousness reveal a fascinating interplay between Cartesian dualism and emergent materialism, neither of which adequately addresses the hard problem of subjective experience.",
            "In the crucible of adversity, one often discovers hitherto untapped reservoirs of resilience; it is precisely when we are pushed beyond our perceived limitations that we transcend our former selves.",
            "The zeitgeist of our era is characterized by an unprecedented confluence of technological innovation and existential uncertainty, compelling us to recalibrate our fundamental assumptions about human agency and purpose.",
        ],
        description="母语水平，地道表达，深度思考"
    ),
]


def print_separator(char="=", length=80):
    print(char * length)


def print_result(result: ProcessingResult, expected_level: str, expected_range: tuple):
    """打印评估结果"""
    actual_score = result.evaluation.get("overall_score", 0)
    actual_level = result.evaluation.get("cefr_level", "?")
    
    # 判断是否符合预期
    in_range = expected_range[0] <= actual_score <= expected_range[1]
    level_match = actual_level == expected_level
    
    status = "✅" if (in_range and level_match) else "❌"
    
    print(f"  {status} 分数: {actual_score} (预期 {expected_range[0]}-{expected_range[1]})")
    print(f"  {status} 等级: {actual_level} (预期 {expected_level})")
    
    if result.evaluation.get("strengths"):
        print(f"  ✨ 优点: {', '.join(result.evaluation['strengths'][:3])}")
    if result.evaluation.get("weaknesses"):
        print(f"  ⚠️  弱点: {', '.join(result.evaluation['weaknesses'][:3])}")
    if result.evaluation.get("corrections"):
        corrections = result.evaluation["corrections"][:2]
        for c in corrections:
            if isinstance(c, dict):
                print(f"  📝 纠错: '{c.get('original', '')}' → '{c.get('corrected', '')}'")
    
    return in_range and level_match


def test_single_user(processor, user: TestUser) -> Dict[str, Any]:
    """测试单个用户"""
    print_separator()
    print(f"👤 测试用户: {user.name}")
    print(f"📖 描述: {user.description}")
    print(f"🎯 预期水平: {user.expected_level} ({user.expected_score_range[0]}-{user.expected_score_range[1]}分)")
    print_separator("-", 60)
    
    results = []
    pass_count = 0
    
    for i, input_text in enumerate(user.inputs, 1):
        print(f"\n📢 输入 {i}: \"{input_text[:60]}{'...' if len(input_text) > 60 else ''}\"")
        
        try:
            result = processor.process_text(input_text)
            passed = print_result(result, user.expected_level, user.expected_score_range)
            results.append({
                "input": input_text,
                "score": result.evaluation.get("overall_score", 0),
                "level": result.evaluation.get("cefr_level", "?"),
                "passed": passed
            })
            if passed:
                pass_count += 1
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            results.append({
                "input": input_text,
                "error": str(e),
                "passed": False
            })
    
    # 汇总
    total = len(user.inputs)
    success_rate = pass_count / total * 100 if total > 0 else 0
    
    print(f"\n📊 用户测试结果: {pass_count}/{total} 通过 ({success_rate:.0f}%)")
    
    return {
        "user": user.name,
        "expected_level": user.expected_level,
        "results": results,
        "pass_count": pass_count,
        "total": total,
        "success_rate": success_rate
    }


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("🧪 评分规则测试 - 验证 CEFR 等级对齐")
    print("=" * 80)
    
    # 创建处理器
    print("\n⏳ 初始化处理器...")
    try:
        processor = create_processor()
        print("✅ 处理器初始化成功")
    except Exception as e:
        print(f"❌ 处理器初始化失败: {e}")
        return
    
    all_results = []
    level_stats = {}
    
    for user in TEST_USERS:
        result = test_single_user(processor, user)
        all_results.append(result)
        
        # 按等级统计
        level = user.expected_level
        if level not in level_stats:
            level_stats[level] = {"pass": 0, "total": 0}
        level_stats[level]["pass"] += result["pass_count"]
        level_stats[level]["total"] += result["total"]
    
    # 总体汇总
    print("\n" + "=" * 80)
    print("📈 总体测试结果汇总")
    print("=" * 80)
    
    total_pass = sum(r["pass_count"] for r in all_results)
    total_tests = sum(r["total"] for r in all_results)
    overall_rate = total_pass / total_tests * 100 if total_tests > 0 else 0
    
    print(f"\n总计: {total_pass}/{total_tests} 通过 ({overall_rate:.1f}%)\n")
    
    print("按 CEFR 等级统计:")
    print("-" * 40)
    for level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        if level in level_stats:
            stats = level_stats[level]
            rate = stats["pass"] / stats["total"] * 100 if stats["total"] > 0 else 0
            status = "✅" if rate >= 70 else "⚠️" if rate >= 50 else "❌"
            print(f"  {status} {level}: {stats['pass']}/{stats['total']} ({rate:.0f}%)")
    
    print("\n" + "=" * 80)
    
    # 判断整体是否通过
    if overall_rate >= 70:
        print("🎉 测试通过！评分规则基本对齐 CEFR 标准")
    elif overall_rate >= 50:
        print("⚠️  测试部分通过，评分规则需要调优")
    else:
        print("❌ 测试失败，评分规则与 CEFR 标准偏差较大")
    
    return all_results


def test_specific_level(level: str):
    """测试特定等级"""
    users = [u for u in TEST_USERS if u.expected_level == level]
    if not users:
        print(f"❌ 没有找到等级 {level} 的测试用户")
        return
    
    print(f"\n🧪 测试 {level} 等级用户")
    processor = create_processor()
    
    for user in users:
        test_single_user(processor, user)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="评分规则测试")
    parser.add_argument("--level", "-l", type=str, help="只测试特定等级 (A1/A2/B1/B2/C1/C2)")
    parser.add_argument("--user", "-u", type=int, help="只测试特定用户 (索引从0开始)")
    
    args = parser.parse_args()
    
    if args.level:
        test_specific_level(args.level.upper())
    elif args.user is not None:
        if 0 <= args.user < len(TEST_USERS):
            processor = create_processor()
            test_single_user(processor, TEST_USERS[args.user])
        else:
            print(f"❌ 用户索引超出范围 (0-{len(TEST_USERS)-1})")
    else:
        run_all_tests()

