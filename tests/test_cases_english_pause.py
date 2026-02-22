"""
维度三：英文语音停顿与干扰测试用例

目标：测试英文场景下的停顿、语气词、拖音、自纠正、非人声干扰等处理能力

测试要求：F12 + 录屏

测试场景覆盖：
- 长静音组织语言
- 英文语气词过滤 (Well, You know, Um)
- 拖音处理
- 深度思考/词汇搜索
- 非人声干扰 (叹气、喝水、背景人声)
- 自我纠正 (I mean, sorry)
- 极限停顿压测
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class EnglishInterferenceType(Enum):
    """英文场景干扰类型枚举"""
    LONG_SILENCE = "长时间静音"
    FILLER_WORDS = "英文语气词"
    TRAILING_SOUND = "拖音处理"
    WORD_SEARCH = "词汇搜索/深度思考"
    NON_SPEECH_NOISE = "非人声干扰"
    EMOTIONAL_PAUSE = "情感沉思"
    BACKGROUND_VOICE = "背景人声"
    SELF_CORRECTION = "自我纠正"
    PHYSIOLOGICAL_NOISE = "生理杂音"
    EXTREME_PAUSE = "极限停顿压测"


class TopicDimension(Enum):
    """话题维度枚举"""
    LIFE_GOAL = "Life Goal"
    INTERESTS = "Interests"
    ROUTINE = "Routine"
    STUDY = "Study"
    FUTURE_PLAN = "Future Plan"
    EMOTION = "Emotion"
    WEATHER = "Weather"
    PHILOSOPHY = "Philosophy"
    RELATIONSHIP = "Relationship"
    HOBBIES = "Hobbies"


@dataclass
class EnglishPauseTestCase:
    """英文停顿与干扰测试用例"""
    id: int
    script: str                             # 英文测试脚本（【】内为停顿或干扰动作）
    topic: TopicDimension                   # 话题维度
    interference_type: EnglishInterferenceType  # 干扰类型
    expected_behavior: str                  # 预期表现（验收标准）
    actual_result: Optional[str] = None     # 实际表现（待填写）
    notes: Optional[str] = None             # 备注


# ============================================================================
# 测试用例定义
# ============================================================================

ENGLISH_PAUSE_TEST_CASES: List[EnglishPauseTestCase] = [
    EnglishPauseTestCase(
        id=1,
        script='I think the most important thing in life is...【静音 3.5s】...to be happy.',
        topic=TopicDimension.LIFE_GOAL,
        interference_type=EnglishInterferenceType.LONG_SILENCE,
        expected_behavior="禁止抢话：用户在组织「to be happy」时，AI 必须保持静默监听。",
        notes="测试 3.5s 静音容忍度，语义未完成（is...）需继续等待"
    ),
    
    EnglishPauseTestCase(
        id=2,
        script='Well... you know...【停顿 1.5s】...I actually...【停顿 2s】...love jazz.',
        topic=TopicDimension.INTERESTS,
        interference_type=EnglishInterferenceType.FILLER_WORDS,
        expected_behavior="语气词过滤：识别到大量「Well/You know」时，AI 不应判定为指令结束，需等核心词「love jazz」。",
        notes="英文废词列表：Well, You know, Actually, Like, I mean, So"
    ),
    
    EnglishPauseTestCase(
        id=3,
        script='My daily routine is...【长拖音：umm————】...waking up at 7 am.',
        topic=TopicDimension.ROUTINE,
        interference_type=EnglishInterferenceType.TRAILING_SOUND,
        expected_behavior="拖音处理：ASR 应忽略拖长的「umm」，VAD 不应在拖音结束后立即截断对话。",
        notes="拖音特征：umm/uh/er 延长发音"
    ),
    
    EnglishPauseTestCase(
        id=4,
        script="I'm interested in... oh, what's that word...【停顿 4s】...architecture!",
        topic=TopicDimension.STUDY,
        interference_type=EnglishInterferenceType.WORD_SEARCH,
        expected_behavior="深度思考：模拟用户搜索单词的极端停顿（4s）。系统需通过语义未完成（in...）判断不应打断。",
        notes="4s 极端停顿，语义线索「interested in...」明确未完成"
    ),
    
    EnglishPauseTestCase(
        id=5,
        script='If I had a million dollars, I would...【叹气声】...buy a big house.',
        topic=TopicDimension.FUTURE_PLAN,
        interference_type=EnglishInterferenceType.NON_SPEECH_NOISE,
        expected_behavior="非人声干扰：过滤叹气、呼吸声，确保这些物理声音不会触发 AI 的错误回复。",
        notes="叹气声不应触发 VAD 结束判定"
    ),
    
    EnglishPauseTestCase(
        id=6,
        script="I feel a bit...【停顿 2.5s】...lonely sometimes, but it's okay.",
        topic=TopicDimension.EMOTION,
        interference_type=EnglishInterferenceType.EMOTIONAL_PAUSE,
        expected_behavior="情感连贯性：情感话题往往伴随沉思，AI 需等整句语气下降（落调）后再开始安慰。",
        notes="情感话题特殊处理，需检测语调下降"
    ),
    
    EnglishPauseTestCase(
        id=7,
        script='My dream job is to be a...【背景杂音：有人叫用户名字】...a director.',
        topic=TopicDimension.FUTURE_PLAN,
        interference_type=EnglishInterferenceType.BACKGROUND_VOICE,
        expected_behavior="抗干扰能力：背景人声不应触发 AI 抢话，AI 应锁定主麦克风的「a director」。",
        notes="需区分主音源与背景音源"
    ),
    
    EnglishPauseTestCase(
        id=8,
        script='I used to live in London... sorry, I mean Manchester.',
        topic=TopicDimension.LIFE_GOAL,
        interference_type=EnglishInterferenceType.SELF_CORRECTION,
        expected_behavior="自纠正逻辑：识别到「I mean」等修正词时，AI 需舍弃前意图，等待新地点。",
        notes="修正词列表：I mean, sorry, actually, no wait, correction"
    ),
    
    EnglishPauseTestCase(
        id=9,
        script='The weather in my city is...【喝水声/吞咽声】...quite humid.',
        topic=TopicDimension.WEATHER,
        interference_type=EnglishInterferenceType.PHYSIOLOGICAL_NOISE,
        expected_behavior="生理杂音过滤：喝水或咳嗽等声音不应被识别为语音结束，需保持连接。",
        notes="生理杂音：喝水、吞咽、咳嗽、清嗓"
    ),
    
    EnglishPauseTestCase(
        id=10,
        script="To be honest...【长达 5s 的极长停顿】...I haven't thought about it yet.",
        topic=TopicDimension.PHILOSOPHY,
        interference_type=EnglishInterferenceType.EXTREME_PAUSE,
        expected_behavior="极限压测：挑战系统 VAD 阈值上限。若 5s 未断，说明动态阈值逻辑架构修改成功。",
        notes="5s 极限测试，验证 VAD 动态阈值上限"
    ),
]


# ============================================================================
# 验收标准汇总
# ============================================================================

ENGLISH_ACCEPTANCE_CRITERIA = {
    EnglishInterferenceType.LONG_SILENCE: {
        "description": "长静音处理",
        "threshold": "3.5s",
        "requirements": [
            "语义未完成时保持静默监听",
            "不在静音中途抢话",
            "等待用户完成整句",
        ],
    },
    
    EnglishInterferenceType.FILLER_WORDS: {
        "description": "英文语气词过滤",
        "filler_word_list": ["Well", "You know", "Actually", "Like", "I mean", "So", "Um", "Uh"],
        "requirements": [
            "识别并过滤英文语气词",
            "等待核心内容词出现",
            "不将语气词视为指令结束",
        ],
    },
    
    EnglishInterferenceType.TRAILING_SOUND: {
        "description": "拖音处理",
        "trailing_sounds": ["umm", "uh", "er", "ah"],
        "requirements": [
            "ASR 正确处理拖长音",
            "VAD 不在拖音后立即截断",
            "不产生乱码识别",
        ],
    },
    
    EnglishInterferenceType.WORD_SEARCH: {
        "description": "词汇搜索/深度思考",
        "threshold": "4s",
        "semantic_cues": ["interested in...", "I want to...", "the word is..."],
        "requirements": [
            "通过语义判断未完成",
            "容忍极端停顿",
            "等待用户找到词汇",
        ],
    },
    
    EnglishInterferenceType.NON_SPEECH_NOISE: {
        "description": "非人声干扰",
        "noise_types": ["叹气声", "呼吸声"],
        "requirements": [
            "过滤非语音声音",
            "不触发错误回复",
            "保持连接状态",
        ],
    },
    
    EnglishInterferenceType.EMOTIONAL_PAUSE: {
        "description": "情感话题沉思",
        "requirements": [
            "检测语调变化（落调）",
            "情感话题给予更多等待时间",
            "整句完成后再回应",
        ],
    },
    
    EnglishInterferenceType.BACKGROUND_VOICE: {
        "description": "背景人声抗干扰",
        "requirements": [
            "区分主音源与背景音",
            "锁定主麦克风输入",
            "背景人声不触发抢话",
        ],
    },
    
    EnglishInterferenceType.SELF_CORRECTION: {
        "description": "自我纠正识别",
        "correction_words": ["I mean", "sorry", "actually", "no wait", "correction", "let me rephrase"],
        "requirements": [
            "识别修正信号词",
            "舍弃前意图",
            "等待纠正后的新内容",
        ],
    },
    
    EnglishInterferenceType.PHYSIOLOGICAL_NOISE: {
        "description": "生理杂音过滤",
        "noise_types": ["喝水声", "吞咽声", "咳嗽声", "清嗓声"],
        "requirements": [
            "过滤生理杂音",
            "不判定为语音结束",
            "保持连接等待",
        ],
    },
    
    EnglishInterferenceType.EXTREME_PAUSE: {
        "description": "极限停顿压测",
        "threshold": "5s",
        "requirements": [
            "VAD 动态阈值支持 5s",
            "语义未完成时继续等待",
            "验证架构修改成功",
        ],
    },
}


# ============================================================================
# 辅助函数
# ============================================================================

def get_test_case_by_id(case_id: int) -> Optional[EnglishPauseTestCase]:
    """根据 ID 获取测试用例"""
    for case in ENGLISH_PAUSE_TEST_CASES:
        if case.id == case_id:
            return case
    return None


def get_test_cases_by_type(interference_type: EnglishInterferenceType) -> List[EnglishPauseTestCase]:
    """根据干扰类型获取测试用例"""
    return [case for case in ENGLISH_PAUSE_TEST_CASES if case.interference_type == interference_type]


def get_test_cases_by_topic(topic: TopicDimension) -> List[EnglishPauseTestCase]:
    """根据话题维度获取测试用例"""
    return [case for case in ENGLISH_PAUSE_TEST_CASES if case.topic == topic]


def print_test_cases_summary():
    """打印测试用例汇总表"""
    print("=" * 120)
    print("维度三：英文语音停顿与干扰测试用例")
    print("测试要求：F12 + 录屏")
    print("=" * 120)
    print()
    print(f"{'序号':<4}{'干扰类型':<15}{'话题':<12}{'测试脚本'}")
    print("-" * 120)
    
    for case in ENGLISH_PAUSE_TEST_CASES:
        script_short = case.script[:60] + "..." if len(case.script) > 60 else case.script
        print(f"{case.id:<4}{case.interference_type.value:<15}{case.topic.value:<12}{script_short}")
    
    print()
    print("=" * 120)


def print_test_report_template():
    """打印测试报告模板"""
    print("=" * 120)
    print("维度三：英文语音停顿与干扰 - 测试报告模板")
    print("=" * 120)
    print()
    
    for case in ENGLISH_PAUSE_TEST_CASES:
        print(f"【用例 {case.id}】{case.interference_type.value} - {case.topic.value}")
        print(f"  脚本: {case.script}")
        print(f"  预期: {case.expected_behavior}")
        print(f"  实际: ________________________________________")
        print(f"  通过: [ ] 是  [ ] 否")
        print()


if __name__ == "__main__":
    print_test_cases_summary()
    
    print("\n详细测试用例：\n")
    for case in ENGLISH_PAUSE_TEST_CASES:
        print(f"[用例 {case.id}] {case.interference_type.value} | {case.topic.value}")
        print(f"  脚本: {case.script}")
        print(f"  预期: {case.expected_behavior}")
        if case.notes:
            print(f"  备注: {case.notes}")
        print()

