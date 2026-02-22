"""
Qwen-Omni 音频评分测试

流程：
1. 使用 TTS 生成测试音频（模拟不同水平用户说话）
2. 用 qwen-omni 模型处理音频并评分
3. 验证评分是否符合 CEFR 标准

注意：TTS 生成的是标准发音，但文本内容包含语法错误，
评分应基于语法、词汇、表达复杂度
"""
import sys
import os
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import tempfile

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.unified_processor import create_processor, ProcessingResult
from services.tts import TTSServiceFactory


@dataclass
class TestCase:
    """测试用例"""
    name: str
    text: str  # 用户说的话（将用 TTS 转成音频）
    expected_level: str  # 预期 CEFR 等级
    expected_score_range: tuple  # (min, max)
    description: str


# 测试用例 - 覆盖所有 CEFR 等级
TEST_CASES = [
    # ========== A1 级别 (0-25) ==========
    TestCase(
        name="A1-纯中文",
        text="我不会说英语，请帮帮我",
        expected_level="A1",
        expected_score_range=(0, 30),
        description="纯中文输入，应该得低分"
    ),
    TestCase(
        name="A1-极简单词",
        text="Hello. Yes. Good.",
        expected_level="A1",
        expected_score_range=(10, 30),
        description="只会最基础的单词"
    ),
    
    # ========== A2 级别 (25-45) ==========
    TestCase(
        name="A2-简单句有错误",
        text="I like play basketball. Yesterday I go to school.",
        expected_level="A2",
        expected_score_range=(25, 50),
        description="简单句子但有明显语法错误"
    ),
    TestCase(
        name="A2-中英混杂",
        text="I want to talk about 足球 with you. 梅西 is very good.",
        expected_level="A2",
        expected_score_range=(25, 50),
        description="中英文混杂"
    ),
    
    # ========== B1 级别 (45-65) ==========
    TestCase(
        name="B1-完整表达",
        text="I went to the cinema last weekend and watched a movie about time travel. It was very interesting.",
        expected_level="B1",
        expected_score_range=(45, 70),
        description="能用完整句子表达，偶有小错"
    ),
    TestCase(
        name="B1-有细节",
        text="Last summer, I traveled to Beijing with my family. We visited the Great Wall and took many photos.",
        expected_level="B1",
        expected_score_range=(45, 70),
        description="能提供细节描述"
    ),
    
    # ========== B2 级别 (65-80) ==========
    TestCase(
        name="B2-复杂句式",
        text="Although I was initially skeptical about the movie, I found myself captivated by its storyline and character development.",
        expected_level="B2",
        expected_score_range=(60, 85),
        description="使用复杂句式和从句"
    ),
    TestCase(
        name="B2-条件句",
        text="If I had known about this opportunity earlier, I would have prepared more thoroughly for the interview.",
        expected_level="B2",
        expected_score_range=(60, 85),
        description="虚拟语气和条件句"
    ),
    
    # ========== C1 级别 (80-92) ==========
    TestCase(
        name="C1-高级词汇",
        text="The proliferation of artificial intelligence has precipitated a paradigm shift in how we conceptualize human-machine interaction.",
        expected_level="C1",
        expected_score_range=(75, 95),
        description="高级词汇和学术表达"
    ),
    TestCase(
        name="C1-复杂论述",
        text="Notwithstanding the considerable obstacles that impeded our progress, we persevered and ultimately achieved unprecedented results in our research.",
        expected_level="C1",
        expected_score_range=(75, 95),
        description="复杂论述和精准用词"
    ),
    
    # ========== C2 级别 (92-100) ==========
    TestCase(
        name="C2-母语水平",
        text="The epistemological underpinnings of contemporary discourse reveal a fascinating interplay between Cartesian dualism and emergent materialism.",
        expected_level="C2",
        expected_score_range=(85, 100),
        description="接近母语水平的深度表达"
    ),
]


def print_separator(char="=", length=80):
    print(char * length)


def generate_audio(tts_service, text: str) -> bytes:
    """使用 TTS 生成音频"""
    try:
        # 使用英文语音生成（即使内容有中文）
        audio_data = tts_service.text_to_speech(text, voice="alloy")
        return audio_data
    except Exception as e:
        print(f"  ⚠️ TTS 生成失败: {e}")
        return None


def run_test(processor, tts_service, test_case: TestCase) -> Dict[str, Any]:
    """运行单个测试"""
    print(f"\n📢 测试: {test_case.name}")
    print(f"   文本: \"{test_case.text[:60]}{'...' if len(test_case.text) > 60 else ''}\"")
    print(f"   预期: {test_case.expected_level} ({test_case.expected_score_range[0]}-{test_case.expected_score_range[1]}分)")
    
    # 1. 生成音频
    print("   ⏳ 生成音频...")
    start_time = time.time()
    audio_data = generate_audio(tts_service, test_case.text)
    tts_time = time.time() - start_time
    
    if not audio_data:
        return {
            "name": test_case.name,
            "error": "TTS 生成失败",
            "passed": False
        }
    
    print(f"   ✅ 音频生成完成 ({len(audio_data)} bytes, {tts_time:.2f}s)")
    
    # 2. 调用 qwen-omni 评分
    print("   ⏳ Qwen-Omni 评分中...")
    start_time = time.time()
    
    try:
        result = processor.process_audio(
            audio_data=audio_data,
            audio_format="mp3"  # OpenAI TTS 输出 mp3
        )
        omni_time = time.time() - start_time
        print(f"   ✅ 评分完成 ({omni_time:.2f}s)")
    except Exception as e:
        print(f"   ❌ 评分失败: {e}")
        return {
            "name": test_case.name,
            "error": str(e),
            "passed": False
        }
    
    # 3. 分析结果
    actual_score = result.evaluation.get("overall_score", 0)
    actual_level = result.evaluation.get("cefr_level", "?")
    
    in_range = test_case.expected_score_range[0] <= actual_score <= test_case.expected_score_range[1]
    level_match = actual_level == test_case.expected_level
    
    # 允许相邻等级的偏差
    level_close = is_level_close(actual_level, test_case.expected_level)
    
    passed = in_range or level_close
    
    status_score = "✅" if in_range else "❌"
    status_level = "✅" if level_match else ("⚠️" if level_close else "❌")
    
    print(f"   {status_score} 分数: {actual_score} (预期 {test_case.expected_score_range[0]}-{test_case.expected_score_range[1]})")
    print(f"   {status_level} 等级: {actual_level} (预期 {test_case.expected_level})")
    
    # 显示转录结果
    if result.transcription:
        print(f"   📝 转录: {result.transcription[:50]}...")
    
    # 显示优缺点
    if result.evaluation.get("strengths"):
        print(f"   ✨ 优点: {', '.join(result.evaluation['strengths'][:2])}")
    if result.evaluation.get("weaknesses"):
        print(f"   ⚠️  弱点: {', '.join(result.evaluation['weaknesses'][:2])}")
    
    return {
        "name": test_case.name,
        "text": test_case.text,
        "expected_level": test_case.expected_level,
        "expected_score_range": test_case.expected_score_range,
        "actual_score": actual_score,
        "actual_level": actual_level,
        "transcription": result.transcription,
        "in_range": in_range,
        "level_match": level_match,
        "passed": passed,
        "tts_time": tts_time,
        "omni_time": omni_time
    }


def is_level_close(actual: str, expected: str) -> bool:
    """检查等级是否相邻（允许一级偏差）"""
    levels = ["A1", "A2", "B1", "B2", "C1", "C2"]
    try:
        actual_idx = levels.index(actual)
        expected_idx = levels.index(expected)
        return abs(actual_idx - expected_idx) <= 1
    except ValueError:
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("🧪 Qwen-Omni 音频评分测试 - 验证 CEFR 等级对齐")
    print("=" * 80)
    
    # 初始化服务
    print("\n⏳ 初始化服务...")
    
    try:
        # 创建 TTS 服务
        tts_service = TTSServiceFactory.create("openai")
        print("✅ TTS 服务初始化成功 (OpenAI)")
    except Exception as e:
        print(f"❌ TTS 服务初始化失败: {e}")
        return
    
    try:
        # 创建处理器（强制使用 qwen-omni）
        processor = create_processor(service_type="qwen-omni")
        print("✅ Qwen-Omni 处理器初始化成功")
    except Exception as e:
        print(f"❌ 处理器初始化失败: {e}")
        return
    
    # 运行测试
    print_separator()
    print("开始测试...")
    print_separator()
    
    results = []
    level_stats = {}
    
    for test_case in TEST_CASES:
        result = run_test(processor, tts_service, test_case)
        results.append(result)
        
        # 统计
        level = test_case.expected_level
        if level not in level_stats:
            level_stats[level] = {"pass": 0, "total": 0}
        level_stats[level]["total"] += 1
        if result.get("passed"):
            level_stats[level]["pass"] += 1
        
        # 避免 API 限流
        time.sleep(1)
    
    # 汇总
    print("\n" + "=" * 80)
    print("📈 测试结果汇总")
    print("=" * 80)
    
    total_pass = sum(1 for r in results if r.get("passed"))
    total_tests = len(results)
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
    
    print("\n" + "-" * 40)
    print("详细结果:")
    print("-" * 40)
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['name']}: {r['error']}")
        else:
            status = "✅" if r["passed"] else "❌"
            print(f"  {status} {r['name']}: {r['actual_score']}分 ({r['actual_level']}) - 预期 {r['expected_level']}")
    
    print("\n" + "=" * 80)
    
    if overall_rate >= 70:
        print("🎉 测试通过！Qwen-Omni 评分基本对齐 CEFR 标准")
    elif overall_rate >= 50:
        print("⚠️  测试部分通过，评分规则可能需要调优")
    else:
        print("❌ 测试失败，评分与 CEFR 标准偏差较大")
    
    return results


def test_single(index: int):
    """测试单个用例"""
    if index < 0 or index >= len(TEST_CASES):
        print(f"❌ 索引超出范围 (0-{len(TEST_CASES)-1})")
        return
    
    test_case = TEST_CASES[index]
    
    print(f"\n🧪 测试单个用例: {test_case.name}")
    print(f"   描述: {test_case.description}")
    
    tts_service = TTSServiceFactory.create("openai")
    processor = create_processor(service_type="qwen-omni")
    
    result = run_test(processor, tts_service, test_case)
    
    print("\n完整评估结果:")
    if "error" not in result:
        print(f"  转录: {result.get('transcription', 'N/A')}")
        print(f"  分数: {result.get('actual_score')}")
        print(f"  等级: {result.get('actual_level')}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Qwen-Omni 音频评分测试")
    parser.add_argument("--index", "-i", type=int, help="只测试特定用例 (索引从0开始)")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有测试用例")
    
    args = parser.parse_args()
    
    if args.list:
        print("测试用例列表:")
        for i, tc in enumerate(TEST_CASES):
            print(f"  {i}: [{tc.expected_level}] {tc.name} - {tc.description}")
    elif args.index is not None:
        test_single(args.index)
    else:
        run_all_tests()

