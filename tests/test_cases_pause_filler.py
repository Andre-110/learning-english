"""
维度二：思考型停顿与语气词干扰测试用例

目标：解决"思考时间被识别为结束"导致的抢话问题

测试场景覆盖：
- 长时间静音中的语义连贯检测
- 语气词/废词过滤
- 拖音处理
- 低分贝自言自语识别
- 意图快速切换处理
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class InterferenceType(Enum):
    """干扰类型枚举"""
    LONG_SILENCE = "长时间静音"
    FILLER_WORDS = "冗余语气词"
    TRAILING_SOUND = "信号拖尾"
    MUMBLING = "插入式思考"
    INTENT_SWITCH = "意图快速切换"


@dataclass
class PauseFillerTestCase:
    """思考型停顿与语气词干扰测试用例"""
    id: int
    speech_text: str                    # 语音文本（带停顿标记）
    interference_type: InterferenceType # 干扰类型
    expected_behavior: str              # 预期表现（验收标准）
    core_intent: str                    # 核心意图/关键词
    notes: Optional[str] = None         # 备注


# ============================================================================
# 测试用例定义
# ============================================================================

PAUSE_FILLER_TEST_CASES: List[PauseFillerTestCase] = [
    PauseFillerTestCase(
        id=6,
        speech_text="我要...(静音 2s)...订一张...(静音 2.5s)...明天的票。",
        interference_type=InterferenceType.LONG_SILENCE,
        expected_behavior="VAD（语音检测）动态阈值生效，感应到语义未完，不抢话、不切断。",
        core_intent="订明天的票",
        notes="测试 VAD 对长静音的容忍度，需要根据语义上下文判断是否继续等待"
    ),
    
    PauseFillerTestCase(
        id=7,
        speech_text="那个...我想问一下...呃...就是...现在的油价。",
        interference_type=InterferenceType.FILLER_WORDS,
        expected_behavior="AI 自动过滤「呃、就是」等废词，在识别到核心词「油价」后才回应。",
        core_intent="查询油价",
        notes="废词列表：呃、那个、就是、这个、嗯、额"
    ),
    
    PauseFillerTestCase(
        id=8,
        speech_text="我想看...(由于思考产生的拖长音：那——个——)...刘德华的电影。",
        interference_type=InterferenceType.TRAILING_SOUND,
        expected_behavior="ASR 需处理拖音，不将其识别为乱码，且 VAD 不在中途判定结束。",
        core_intent="看刘德华的电影",
        notes="拖音特征：元音延长、音调稳定、非正常语速"
    ),
    
    PauseFillerTestCase(
        id=9,
        speech_text="帮我定个闹钟，(小声自言自语：几点合适呢...)...八点吧。",
        interference_type=InterferenceType.MUMBLING,
        expected_behavior="AI 需识别出中间的低分贝声音为自言自语，并在听到「八点」后设定。",
        core_intent="定八点闹钟",
        notes="低分贝阈值判断，区分自言自语与正式指令"
    ),
    
    PauseFillerTestCase(
        id=10,
        speech_text="帮我查一下，算了，帮我放首歌吧。",
        interference_type=InterferenceType.INTENT_SWITCH,
        expected_behavior="AI 需舍弃前半句失效意图，响应最新的「放首歌」指令。",
        core_intent="放首歌",
        notes="取消词检测：算了、不用了、等等、不对"
    ),
]


# ============================================================================
# 验收标准汇总
# ============================================================================

ACCEPTANCE_CRITERIA = {
    InterferenceType.LONG_SILENCE: {
        "description": "长静音处理",
        "requirements": [
            "VAD 动态阈值支持 2-3 秒静音不切断",
            "语义未完成时继续等待",
            "语义完成后正常切断",
        ],
        "anti_patterns": [
            "中途抢话",
            "静音超过 1.5 秒立即切断",
        ]
    },
    
    InterferenceType.FILLER_WORDS: {
        "description": "废词过滤",
        "requirements": [
            "识别并过滤常见语气词",
            "等待核心意图词出现后再响应",
            "转录结果可保留废词（标注）",
        ],
        "filler_word_list": ["呃", "嗯", "那个", "就是", "这个", "额", "然后"],
        "anti_patterns": [
            "将废词作为意图处理",
            "废词后立即响应",
        ]
    },
    
    InterferenceType.TRAILING_SOUND: {
        "description": "拖音处理",
        "requirements": [
            "ASR 正确处理拖长音",
            "不产生乱码或重复字符",
            "VAD 不在拖音中途切断",
        ],
        "anti_patterns": [
            "拖音识别为乱码",
            "拖音触发 VAD 结束",
        ]
    },
    
    InterferenceType.MUMBLING: {
        "description": "自言自语识别",
        "requirements": [
            "检测低分贝语音段",
            "区分自言自语与正式指令",
            "等待正常音量指令后响应",
        ],
        "anti_patterns": [
            "响应自言自语内容",
            "低分贝语音触发中断",
        ]
    },
    
    InterferenceType.INTENT_SWITCH: {
        "description": "意图切换处理",
        "requirements": [
            "识别取消/切换信号词",
            "舍弃已失效意图",
            "响应最新有效意图",
        ],
        "cancel_words": ["算了", "不用了", "等等", "不对", "不是"],
        "anti_patterns": [
            "执行已取消的意图",
            "同时执行新旧意图",
        ]
    },
}


# ============================================================================
# 辅助函数
# ============================================================================

def get_test_case_by_id(case_id: int) -> Optional[PauseFillerTestCase]:
    """根据 ID 获取测试用例"""
    for case in PAUSE_FILLER_TEST_CASES:
        if case.id == case_id:
            return case
    return None


def get_test_cases_by_type(interference_type: InterferenceType) -> List[PauseFillerTestCase]:
    """根据干扰类型获取测试用例"""
    return [case for case in PAUSE_FILLER_TEST_CASES if case.interference_type == interference_type]


def print_test_cases_summary():
    """打印测试用例汇总表"""
    print("=" * 100)
    print("维度二：思考型停顿与语气词干扰测试用例")
    print("=" * 100)
    print()
    print(f"{'序号':<6}{'干扰类型':<15}{'核心意图':<20}{'语音文本'}")
    print("-" * 100)
    
    for case in PAUSE_FILLER_TEST_CASES:
        print(f"{case.id:<6}{case.interference_type.value:<15}{case.core_intent:<20}{case.speech_text[:50]}...")
    
    print()
    print("=" * 100)


if __name__ == "__main__":
    print_test_cases_summary()
    
    print("\n详细测试用例：\n")
    for case in PAUSE_FILLER_TEST_CASES:
        print(f"[用例 {case.id}] {case.interference_type.value}")
        print(f"  语音文本: {case.speech_text}")
        print(f"  核心意图: {case.core_intent}")
        print(f"  预期表现: {case.expected_behavior}")
        if case.notes:
            print(f"  备注: {case.notes}")
        print()

