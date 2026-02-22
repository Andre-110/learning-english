"""
对话测试 Agent - 模拟人类与系统进行多轮文字交互

用途：
1. 自动化测试对话系统的各种场景
2. 验证节奏引导、难度调整、评分间隔等功能
3. 生成测试报告

使用方法：
    python tests/conversation_agent.py --scenario short_answers --turns 10
    python tests/conversation_agent.py --scenario mixed_language --turns 5
    python tests/conversation_agent.py --scenario all --turns 8
"""

import sys
import os
import json
import random
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompts.templates import (
    get_interaction_system_prompt,
    get_pipeline_system_prompt,
    get_pipeline_user_prompt,
    get_initial_question_prompt,
    analyze_conversation_rhythm,
)


class UserPersona(Enum):
    """用户人设类型"""
    SHORT_RESPONDER = "short_responder"      # 总是给短答
    VERBOSE_RESPONDER = "verbose_responder"  # 总是长篇大论
    MIXED_LANGUAGE = "mixed_language"        # 中英混用
    HESITANT = "hesitant"                    # 犹豫、不确定
    ENTHUSIASTIC = "enthusiastic"            # 热情、主动
    NORMAL = "normal"                        # 正常对话


@dataclass
class TestScenario:
    """测试场景配置"""
    name: str
    persona: UserPersona
    cefr_level: str = "A2"
    interests: List[str] = field(default_factory=lambda: ["reading", "movies"])
    expected_behaviors: List[str] = field(default_factory=list)
    description: str = ""


# 预定义测试场景
SCENARIOS = {
    "short_answers": TestScenario(
        name="连续短答测试",
        persona=UserPersona.SHORT_RESPONDER,
        cefr_level="A2",
        expected_behaviors=[
            "AI 应该在 2-3 轮短答后建议换话题",
            "节奏引导应该触发 switch_topic 策略",
        ],
        description="测试连续短答时系统是否会调整策略"
    ),
    "mixed_language": TestScenario(
        name="中英混用测试",
        persona=UserPersona.MIXED_LANGUAGE,
        cefr_level="A1",
        expected_behaviors=[
            "AI 应该用英语回复",
            "AI 不应该批评用户使用中文",
            "AI 应该自然地提供英文表达",
        ],
        description="测试中英混用时系统的处理方式"
    ),
    "verbose": TestScenario(
        name="长回答测试",
        persona=UserPersona.VERBOSE_RESPONDER,
        cefr_level="B2",
        expected_behaviors=[
            "AI 应该总结并延伸话题",
            "节奏引导应该触发 summarize 策略",
        ],
        description="测试长回答时系统是否会总结"
    ),
    "hesitant": TestScenario(
        name="犹豫用户测试",
        persona=UserPersona.HESITANT,
        cefr_level="A1",
        expected_behaviors=[
            "AI 应该给予鼓励",
            "AI 不应该连续追问",
        ],
        description="测试面对犹豫用户时系统的鼓励策略"
    ),
    "normal": TestScenario(
        name="正常对话测试",
        persona=UserPersona.NORMAL,
        cefr_level="B1",
        expected_behaviors=[
            "对话应该自然流畅",
            "AI 应该问情境型开放问题",
        ],
        description="测试正常对话流程"
    ),
}


class SimulatedUser:
    """模拟用户 - 根据人设生成回复"""
    
    def __init__(self, persona: UserPersona, cefr_level: str = "A2"):
        self.persona = persona
        self.cefr_level = cefr_level
        self.turn_count = 0
        
        # 预定义回复模板
        self.short_responses = [
            "Yes", "No", "Maybe", "OK", "Sure", "I think so",
            "Not really", "I guess", "Hmm", "Yeah",
        ]
        
        self.verbose_responses = [
            "Well, that's a really interesting question. Let me think about it. "
            "I would say that I have many hobbies and interests. For example, "
            "I really enjoy reading books, especially science fiction and fantasy novels. "
            "I also like watching movies on weekends with my family.",
            
            "Oh, I have so many things to share about this topic! "
            "First of all, I think it's important to understand the context. "
            "In my experience, I've found that taking time to reflect on things "
            "really helps me appreciate them more. What do you think about that?",
            
            "That reminds me of something that happened last week. "
            "I was walking in the park when I saw a beautiful sunset. "
            "It made me think about how amazing nature is. "
            "I took some photos and shared them with my friends. "
            "They all said it was really beautiful.",
        ]
        
        self.mixed_language_responses = [
            "我喜欢 reading books, especially 小说",
            "Yes, I like 看电影, it's very 有意思",
            "My favorite food is 火锅, very delicious",
            "I work in 北京, it's a big city",
            "周末我喜欢 go shopping with friends",
            "我觉得 English is 很难 but 有趣",
        ]
        
        self.hesitant_responses = [
            "Um... I'm not sure... maybe...",
            "I don't know... let me think...",
            "Hmm... it's difficult to say...",
            "I'm not good at this...",
            "Sorry, I don't understand...",
            "Can you... um... say that again?",
        ]
        
        self.enthusiastic_responses = [
            "Oh wow! That's such a great question! I absolutely love talking about this!",
            "Yes! Definitely! I'm so passionate about this topic!",
            "That's amazing! I have so many thoughts on this!",
            "I love it! Let me tell you all about my experience!",
        ]
        
        self.normal_responses = [
            "I like reading books in my free time.",
            "My favorite movie is The Shawshank Redemption.",
            "I usually go to the gym on weekends.",
            "I've been learning English for about two years.",
            "I work as a software engineer.",
            "I enjoy cooking dinner for my family.",
            "Last weekend I visited a museum.",
            "I'm planning to travel to Japan next year.",
        ]
    
    def generate_response(self, ai_message: str) -> str:
        """根据人设生成用户回复"""
        self.turn_count += 1
        
        if self.persona == UserPersona.SHORT_RESPONDER:
            return random.choice(self.short_responses)
        
        elif self.persona == UserPersona.VERBOSE_RESPONDER:
            return random.choice(self.verbose_responses)
        
        elif self.persona == UserPersona.MIXED_LANGUAGE:
            return random.choice(self.mixed_language_responses)
        
        elif self.persona == UserPersona.HESITANT:
            return random.choice(self.hesitant_responses)
        
        elif self.persona == UserPersona.ENTHUSIASTIC:
            return random.choice(self.enthusiastic_responses)
        
        else:  # NORMAL
            return random.choice(self.normal_responses)


class MockLLMService:
    """
    模拟 LLM 服务 - 使用 Prompt 模板但不调用真实 API
    
    如果需要真实测试，可以替换为实际的 LLM 调用
    """
    
    def __init__(self, user_profile: Dict[str, Any]):
        self.user_profile = user_profile
        self.conversation_history: List[Dict[str, str]] = []
    
    def get_initial_question(self) -> str:
        """生成初始问题"""
        # 使用真实的 Prompt 模板
        prompt = get_initial_question_prompt(self.user_profile)
        
        # 模拟 LLM 输出（实际测试时可以调用真实 API）
        initial_questions = [
            "Hey! What's something that made you smile today?",
            "Hi there! If you had a free day tomorrow, what would you do?",
            "Hello! What's been the highlight of your week so far?",
            "Hey! What's a hobby you've been wanting to try?",
        ]
        return random.choice(initial_questions)
    
    def generate_response(self, user_text: str) -> Dict[str, Any]:
        """生成 AI 回复"""
        # 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_text
        })
        
        # 分析节奏
        rhythm = analyze_conversation_rhythm(self.conversation_history)
        
        # 获取 Prompt（用于验证）
        system_prompt = get_interaction_system_prompt(self.user_profile)
        user_prompt = get_pipeline_user_prompt(user_text, self.conversation_history)
        
        # 模拟 AI 回复（根据节奏策略调整）
        strategy = rhythm["suggested_strategy"]
        
        if strategy == "switch_topic":
            response = "I see! Let's talk about something else. What do you enjoy doing on weekends?"
        elif strategy == "lighten":
            response = "Got it! Would you rather talk about movies or music?"
        elif strategy == "summarize":
            response = "That's wonderful that you shared so much! What's the most memorable part?"
        else:
            response = "That's interesting! Tell me more about what you enjoy most about it."
        
        # 添加 AI 回复到历史
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })
        
        return {
            "response": response,
            "rhythm_analysis": rhythm,
            "system_prompt_preview": system_prompt[:200] + "...",
            "user_prompt_preview": user_prompt[:200] + "...",
        }


@dataclass
class ConversationTurn:
    """单轮对话记录"""
    turn_number: int
    user_message: str
    ai_response: str
    rhythm_analysis: Dict[str, Any]
    timestamp: float = 0


@dataclass
class TestResult:
    """测试结果"""
    scenario_name: str
    total_turns: int
    conversation: List[ConversationTurn]
    rhythm_changes: List[Dict[str, Any]]
    expected_behaviors: List[str]
    observations: List[str]
    passed: bool = True


class ConversationAgent:
    """对话测试 Agent"""
    
    def __init__(self, scenario: TestScenario):
        self.scenario = scenario
        self.user_profile = {
            "cefr_level": scenario.cefr_level,
            "interests": scenario.interests,
            "overall_score": 50,
        }
        self.user = SimulatedUser(scenario.persona, scenario.cefr_level)
        self.llm = MockLLMService(self.user_profile)
        self.conversation: List[ConversationTurn] = []
        self.rhythm_changes: List[Dict[str, Any]] = []
    
    def run(self, num_turns: int = 5) -> TestResult:
        """运行多轮对话测试"""
        print(f"\n{'='*60}")
        print(f"场景: {self.scenario.name}")
        print(f"人设: {self.scenario.persona.value}")
        print(f"等级: {self.scenario.cefr_level}")
        print(f"轮次: {num_turns}")
        print(f"{'='*60}")
        
        # 初始问题
        initial_question = self.llm.get_initial_question()
        print(f"\n🤖 AI: {initial_question}")
        
        last_strategy = "continue"
        observations = []
        
        for turn in range(1, num_turns + 1):
            # 用户回复
            user_response = self.user.generate_response(initial_question)
            print(f"\n👤 User (Turn {turn}): {user_response}")
            
            # AI 回复
            result = self.llm.generate_response(user_response)
            ai_response = result["response"]
            rhythm = result["rhythm_analysis"]
            
            print(f"🤖 AI: {ai_response}")
            print(f"   📊 节奏: {rhythm['suggested_strategy']} "
                  f"(连续短答: {rhythm['consecutive_short_count']}, "
                  f"长度: {rhythm['last_response_length']})")
            
            # 记录策略变化
            current_strategy = rhythm["suggested_strategy"]
            if current_strategy != last_strategy:
                change = {
                    "turn": turn,
                    "from": last_strategy,
                    "to": current_strategy,
                }
                self.rhythm_changes.append(change)
                observations.append(
                    f"Turn {turn}: 策略从 {last_strategy} 变为 {current_strategy}"
                )
                last_strategy = current_strategy
            
            # 记录对话
            self.conversation.append(ConversationTurn(
                turn_number=turn,
                user_message=user_response,
                ai_response=ai_response,
                rhythm_analysis=rhythm,
            ))
            
            initial_question = ai_response
        
        # 生成测试结果
        return TestResult(
            scenario_name=self.scenario.name,
            total_turns=num_turns,
            conversation=self.conversation,
            rhythm_changes=self.rhythm_changes,
            expected_behaviors=self.scenario.expected_behaviors,
            observations=observations,
        )


def print_test_report(results: List[TestResult]):
    """打印测试报告"""
    print("\n" + "="*60)
    print("                    测试报告")
    print("="*60)
    
    for result in results:
        print(f"\n📋 场景: {result.scenario_name}")
        print(f"   轮次: {result.total_turns}")
        print(f"   策略变化: {len(result.rhythm_changes)} 次")
        
        if result.rhythm_changes:
            print("   变化详情:")
            for change in result.rhythm_changes:
                print(f"      - Turn {change['turn']}: {change['from']} → {change['to']}")
        
        print("   预期行为:")
        for behavior in result.expected_behaviors:
            print(f"      ✓ {behavior}")
        
        if result.observations:
            print("   实际观察:")
            for obs in result.observations:
                print(f"      • {obs}")
    
    print("\n" + "="*60)
    print("                    测试完成")
    print("="*60)


def run_all_scenarios(num_turns: int = 5):
    """运行所有测试场景"""
    results = []
    
    for scenario_name, scenario in SCENARIOS.items():
        agent = ConversationAgent(scenario)
        result = agent.run(num_turns)
        results.append(result)
    
    print_test_report(results)
    return results


def run_single_scenario(scenario_name: str, num_turns: int = 5):
    """运行单个测试场景"""
    if scenario_name not in SCENARIOS:
        print(f"❌ 未知场景: {scenario_name}")
        print(f"可用场景: {list(SCENARIOS.keys())}")
        return None
    
    scenario = SCENARIOS[scenario_name]
    agent = ConversationAgent(scenario)
    result = agent.run(num_turns)
    print_test_report([result])
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="对话测试 Agent")
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        default="all",
        help=f"测试场景: {list(SCENARIOS.keys())} 或 'all'"
    )
    parser.add_argument(
        "--turns", "-t",
        type=int,
        default=5,
        help="对话轮次 (默认: 5)"
    )
    
    args = parser.parse_args()
    
    if args.scenario == "all":
        run_all_scenarios(args.turns)
    else:
        run_single_scenario(args.scenario, args.turns)
