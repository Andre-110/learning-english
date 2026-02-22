"""
维度四：网络异常与 ASR 异常测试用例

目标：测试网络不稳定和 ASR 服务异常情况下的系统鲁棒性

测试要求：F12 + 录屏

测试场景覆盖：
- 丢包 (Packet Loss)
- ASR 重连
- 延迟 (Delay)
- 抖动 (Jitter)
- 断网 (Disconnect)
- 静音恢复
- TCP 重传
- 带宽下降
- WebSocket 握手失败
- 空音频包
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class NetworkIssueType(Enum):
    """网络/ASR 异常类型枚举"""
    PACKET_LOSS = "丢包 (Loss)"
    ASR_RECONNECT = "ASR 重连"
    DELAY = "延迟 (Delay)"
    JITTER = "抖动 (Jitter)"
    TOTAL_DISCONNECT = "彻底断网"
    SILENCE_RECOVERY = "静音恢复"
    TCP_RETRANSMISSION = "TCP 重传"
    BANDWIDTH_DROP = "带宽下降"
    WS_HANDSHAKE_FAIL = "WS 握手失败"
    EMPTY_AUDIO_PACKETS = "空音频包"


class TopicDimension(Enum):
    """话题维度枚举"""
    HOBBIES = "Hobbies"
    STUDY = "Study"
    FUTURE_PLAN = "Future Plan"
    WEATHER = "Weather"
    RELATIONSHIP = "Relationship"
    LIFE_GOAL = "Life Goal"
    INTERESTS = "Interests"
    EMOTION = "Emotion"


@dataclass
class NetworkASRTestCase:
    """网络/ASR 异常测试用例"""
    id: int
    script: str                         # 英文测试脚本（【】内为模拟异常）
    topic: TopicDimension               # 话题维度
    issue_type: NetworkIssueType        # 异常类型
    expected_behavior: str              # 预期表现（验收标准）
    actual_result: Optional[str] = None # 实际表现（待填写）
    notes: Optional[str] = None         # 备注


# ============================================================================
# 测试用例定义
# ============================================================================

NETWORK_ASR_TEST_CASES: List[NetworkASRTestCase] = [
    NetworkASRTestCase(
        id=1,
        script='I think my biggest hobby is 【Loss 800ms】 playing basketball with friends.',
        topic=TopicDimension.HOBBIES,
        issue_type=NetworkIssueType.PACKET_LOSS,
        expected_behavior="AI 必须完整识别出「playing basketball」，不能漏掉关键动作。",
        notes="800ms 丢包，验证 ASR 对关键词的补全能力"
    ),
    
    NetworkASRTestCase(
        id=2,
        script="I'm planning to 【ASR Reconnect】 study abroad in London next year.",
        topic=TopicDimension.STUDY,
        issue_type=NetworkIssueType.ASR_RECONNECT,
        expected_behavior="无损修复：重连后 AI 应准确捕捉到目的地「London」，并针对留学计划提问。",
        notes="ASR 服务重连场景，验证上下文保持"
    ),
    
    NetworkASRTestCase(
        id=3,
        script='Regarding my career, 【Delay 2s】 I want to be a software engineer.',
        topic=TopicDimension.FUTURE_PLAN,
        issue_type=NetworkIssueType.DELAY,
        expected_behavior="即使 ASR 处理变慢，界面也应显示实时识别的单词，避免用户以为 App 挂了。",
        notes="2s 延迟，验证 UI 实时反馈机制"
    ),
    
    NetworkASRTestCase(
        id=4,
        script='The weather 【Jitter】 today is 【Jitter】 much better than yesterday.',
        topic=TopicDimension.WEATHER,
        issue_type=NetworkIssueType.JITTER,
        expected_behavior="文本去重：不能因为网络抖动识别出重复的「today is today is」。",
        notes="抖动导致重复包，验证去重逻辑"
    ),
    
    NetworkASRTestCase(
        id=5,
        script='Honestly, my 【Total Disconnect】 ...',
        topic=TopicDimension.RELATIONSHIP,
        issue_type=NetworkIssueType.TOTAL_DISCONNECT,
        expected_behavior="彻底断网：AI 应温和提示「Oops, connection lost. Can you repeat that?」而非空白响应。",
        notes="完全断网，验证优雅降级和用户提示"
    ),
    
    NetworkASRTestCase(
        id=6,
        script='In the future, I hope to 【2s Silence Recovery】 travel around the world.',
        topic=TopicDimension.LIFE_GOAL,
        issue_type=NetworkIssueType.SILENCE_RECOVERY,
        expected_behavior="模拟长延时空洞：恢复后 AI 需通过上下文逻辑补齐「I hope to」后面的内容。",
        notes="2s 静音空洞，验证上下文补全"
    ),
    
    NetworkASRTestCase(
        id=7,
        script='Talking about my ex, 【TCP Retransmission】 it was a complicated story.',
        topic=TopicDimension.RELATIONSHIP,
        issue_type=NetworkIssueType.TCP_RETRANSMISSION,
        expected_behavior="压力测试：模拟数据包重传。AI 应理解语义，不被重复的音频碎片干扰。",
        notes="TCP 重传导致重复数据，验证去重和语义理解"
    ),
    
    NetworkASRTestCase(
        id=8,
        script='I really enjoy 【Bandwidth Drop】 listening to jazz music at night.',
        topic=TopicDimension.INTERESTS,
        issue_type=NetworkIssueType.BANDWIDTH_DROP,
        expected_behavior="低采样率识别：即使网络变差音质下降，AI 也要能从模糊音频中识别出「jazz music」。",
        notes="带宽下降导致音质变差，验证低质量音频识别"
    ),
    
    NetworkASRTestCase(
        id=9,
        script='Could you 【WS Handshake Fail】 give me some advice on learning English?',
        topic=TopicDimension.STUDY,
        issue_type=NetworkIssueType.WS_HANDSHAKE_FAIL,
        expected_behavior="启动异常：如果刚开始说话就建联失败，系统需秒级切换备份链路，不打断用户表达。",
        notes="WebSocket 握手失败，验证备份链路切换"
    ),
    
    NetworkASRTestCase(
        id=10,
        script="I'm a bit 【Empty Audio Packets】 stressed about my interview tomorrow.",
        topic=TopicDimension.EMOTION,
        issue_type=NetworkIssueType.EMPTY_AUDIO_PACKETS,
        expected_behavior="假死检测：如果 ASR 包显示正常但 LLM 没反应，3s 后系统需主动引导：「I'm listening, go on.」",
        notes="空音频包导致假死，验证超时引导机制"
    ),
]


# ============================================================================
# 验收标准汇总
# ============================================================================

NETWORK_ASR_ACCEPTANCE_CRITERIA = {
    NetworkIssueType.PACKET_LOSS: {
        "description": "丢包处理",
        "threshold": "800ms",
        "requirements": [
            "关键词不丢失",
            "ASR 具备补全能力",
            "用户无感知",
        ],
        "anti_patterns": [
            "关键动作词被跳过",
            "句子残缺不完整",
        ]
    },
    
    NetworkIssueType.ASR_RECONNECT: {
        "description": "ASR 重连",
        "requirements": [
            "重连后上下文保持",
            "关键信息不丢失",
            "无缝衔接对话",
        ],
        "anti_patterns": [
            "重连后丢失前文",
            "需要用户重复",
        ]
    },
    
    NetworkIssueType.DELAY: {
        "description": "延迟处理",
        "threshold": "2s",
        "requirements": [
            "UI 显示实时识别进度",
            "用户知道系统在工作",
            "避免假死感",
        ],
        "ui_feedback": [
            "显示正在识别的文字",
            "加载动画",
            "进度指示",
        ]
    },
    
    NetworkIssueType.JITTER: {
        "description": "抖动处理",
        "requirements": [
            "文本去重",
            "不输出重复词",
            "保持句子流畅",
        ],
        "anti_patterns": [
            "重复词输出",
            "句子结构混乱",
        ]
    },
    
    NetworkIssueType.TOTAL_DISCONNECT: {
        "description": "彻底断网",
        "requirements": [
            "温和的错误提示",
            "引导用户重试",
            "不出现空白响应",
        ],
        "expected_prompt": "Oops, connection lost. Can you repeat that?",
        "anti_patterns": [
            "空白响应",
            "界面卡死",
            "无提示",
        ]
    },
    
    NetworkIssueType.SILENCE_RECOVERY: {
        "description": "静音恢复",
        "threshold": "2s",
        "requirements": [
            "通过上下文补全",
            "恢复后语义连贯",
            "不丢失意图",
        ],
    },
    
    NetworkIssueType.TCP_RETRANSMISSION: {
        "description": "TCP 重传",
        "requirements": [
            "去除重复音频碎片",
            "语义理解不受干扰",
            "输出流畅",
        ],
    },
    
    NetworkIssueType.BANDWIDTH_DROP: {
        "description": "带宽下降",
        "requirements": [
            "低质量音频识别",
            "关键词仍可识别",
            "降级但可用",
        ],
    },
    
    NetworkIssueType.WS_HANDSHAKE_FAIL: {
        "description": "WebSocket 握手失败",
        "requirements": [
            "秒级切换备份链路",
            "不打断用户表达",
            "自动重连",
        ],
        "recovery_time": "< 1s",
    },
    
    NetworkIssueType.EMPTY_AUDIO_PACKETS: {
        "description": "空音频包/假死检测",
        "timeout": "3s",
        "requirements": [
            "检测假死状态",
            "主动引导用户",
            "超时后提示",
        ],
        "expected_prompt": "I'm listening, go on.",
    },
}


# ============================================================================
# 辅助函数
# ============================================================================

def get_test_case_by_id(case_id: int) -> Optional[NetworkASRTestCase]:
    """根据 ID 获取测试用例"""
    for case in NETWORK_ASR_TEST_CASES:
        if case.id == case_id:
            return case
    return None


def get_test_cases_by_type(issue_type: NetworkIssueType) -> List[NetworkASRTestCase]:
    """根据异常类型获取测试用例"""
    return [case for case in NETWORK_ASR_TEST_CASES if case.issue_type == issue_type]


def get_test_cases_by_topic(topic: TopicDimension) -> List[NetworkASRTestCase]:
    """根据话题维度获取测试用例"""
    return [case for case in NETWORK_ASR_TEST_CASES if case.topic == topic]


def print_test_cases_summary():
    """打印测试用例汇总表"""
    print("=" * 120)
    print("维度四：网络异常与 ASR 异常测试用例")
    print("测试要求：F12 + 录屏")
    print("=" * 120)
    print()
    print(f"{'序号':<4}{'异常类型':<18}{'话题':<12}{'测试脚本'}")
    print("-" * 120)
    
    for case in NETWORK_ASR_TEST_CASES:
        script_short = case.script[:55] + "..." if len(case.script) > 55 else case.script
        print(f"{case.id:<4}{case.issue_type.value:<18}{case.topic.value:<12}{script_short}")
    
    print()
    print("=" * 120)


def print_test_report_template():
    """打印测试报告模板"""
    print("=" * 120)
    print("维度四：网络异常与 ASR 异常 - 测试报告模板")
    print("=" * 120)
    print()
    
    for case in NETWORK_ASR_TEST_CASES:
        print(f"【用例 {case.id}】{case.issue_type.value} - {case.topic.value}")
        print(f"  脚本: {case.script}")
        print(f"  预期: {case.expected_behavior}")
        print(f"  实际: ________________________________________")
        print(f"  通过: [ ] 是  [ ] 否")
        print()


if __name__ == "__main__":
    print_test_cases_summary()
    
    print("\n详细测试用例：\n")
    for case in NETWORK_ASR_TEST_CASES:
        print(f"[用例 {case.id}] {case.issue_type.value} | {case.topic.value}")
        print(f"  脚本: {case.script}")
        print(f"  预期: {case.expected_behavior}")
        if case.notes:
            print(f"  备注: {case.notes}")
        print()

