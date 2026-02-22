"""
真实 LLM 对话测试 - 使用实际 API 进行多轮对话

用法：
    python tests/real_conversation_test.py --turns 5
    python tests/real_conversation_test.py --scenario short_answers --turns 6
"""

import sys
import os
import json
import random
import time
from typing import Optional, List, Dict, Any

# 加载环境变量（手动解析 .env 文件）
def load_env_file(filepath=".env"):
    """手动加载 .env 文件"""
    import os
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filepath)
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env_file()

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from prompts.templates import (
    get_interaction_system_prompt,
    get_pipeline_system_prompt,
    get_pipeline_user_prompt,
    get_initial_question_prompt,
    analyze_conversation_rhythm,
    get_rhythm_instruction,
)


class RealLLMService:
    """真实 LLM 服务 - 使用 requests 调用 OpenAI API"""
    
    def __init__(self, user_profile: Dict[str, Any]):
        self.user_profile = user_profile
        self.conversation_history: List[Dict[str, str]] = []
        
        # API 配置
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        
        print(f"[LLM] 使用模型: {self.model}")
        print(f"[LLM] Base URL: {self.base_url}")
    
    def _call_api(self, messages: List[Dict], max_tokens: int = 150, temperature: float = 0.7) -> Dict:
        """调用 OpenAI API"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def get_initial_question(self) -> str:
        """生成初始问题"""
        prompt = get_initial_question_prompt(self.user_profile)
        
        try:
            result = self._call_api(
                messages=[{"role": "system", "content": prompt}],
                max_tokens=100,
                temperature=0.8,
            )
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[LLM] 初始问题生成失败: {e}")
            return "Hey! What's something interesting that happened to you recently?"
    
    def generate_response(self, user_text: str) -> Dict[str, Any]:
        """生成 AI 回复"""
        # 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_text
        })
        
        # 分析节奏
        rhythm = analyze_conversation_rhythm(self.conversation_history)
        rhythm_instruction = get_rhythm_instruction(self.conversation_history)
        
        # 获取 System Prompt
        system_prompt = get_pipeline_system_prompt(self.user_profile)
        
        # 获取 User Prompt（包含节奏引导）
        user_prompt = get_pipeline_user_prompt(user_text, self.conversation_history)
        
        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # 添加历史对话（最近 3 轮）
        recent_history = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history[:-1]
        for msg in recent_history:
            messages.append(msg)
        
        # 添加当前用户消息（带节奏引导）
        messages.append({"role": "user", "content": user_prompt})
        
        try:
            start_time = time.time()
            result = self._call_api(messages=messages, max_tokens=150, temperature=0.7)
            latency = time.time() - start_time
            
            ai_response = result["choices"][0]["message"]["content"].strip()
            tokens = result.get("usage", {}).get("total_tokens", 0)
            
            # 添加 AI 回复到历史
            self.conversation_history.append({
                "role": "assistant",
                "content": ai_response
            })
            
            return {
                "response": ai_response,
                "rhythm_analysis": rhythm,
                "rhythm_instruction": rhythm_instruction[:100] if rhythm_instruction else "",
                "latency": round(latency, 2),
                "tokens": tokens,
            }
            
        except Exception as e:
            print(f"[LLM] 生成回复失败: {e}")
            return {
                "response": f"[Error: {str(e)[:50]}]",
                "rhythm_analysis": rhythm,
                "rhythm_instruction": "",
                "latency": 0,
                "tokens": 0,
            }


class SimulatedUser:
    """模拟用户"""
    
    def __init__(self, persona: str = "normal"):
        self.persona = persona
        self.turn_count = 0
        
        self.responses = {
            "short": ["Yes", "No", "Maybe", "OK", "Sure", "I think so", "Not really"],
            "mixed": [
                "我喜欢 reading books",
                "Yes, I like 看电影",
                "My favorite food is 火锅",
                "周末我喜欢 go shopping",
            ],
            "verbose": [
                "That's a really great question! Let me think about it. I would say that I have many hobbies. For example, I enjoy reading books, especially science fiction. I also like watching movies with my family on weekends.",
                "Oh, I have so many things to share! In my experience, I've found that taking time to reflect really helps me. What do you think about that?",
            ],
            "normal": [
                "I like reading books in my free time.",
                "My favorite movie is The Shawshank Redemption.",
                "I usually go to the gym on weekends.",
                "I work as a software engineer.",
                "I enjoy cooking dinner for my family.",
            ],
        }
    
    def generate_response(self, ai_message: str) -> str:
        self.turn_count += 1
        return random.choice(self.responses.get(self.persona, self.responses["normal"]))


def run_real_conversation(
    persona: str = "normal",
    cefr_level: str = "A2",
    num_turns: int = 5
):
    """运行真实 LLM 对话测试"""
    
    print("\n" + "="*70)
    print("              真实 LLM 对话测试")
    print("="*70)
    print(f"人设: {persona}")
    print(f"等级: {cefr_level}")
    print(f"轮次: {num_turns}")
    print("="*70)
    
    user_profile = {
        "cefr_level": cefr_level,
        "interests": ["reading", "movies", "music"],
        "overall_score": 50,
    }
    
    llm = RealLLMService(user_profile)
    user = SimulatedUser(persona)
    
    # 获取初始问题
    print("\n🔄 正在生成初始问题...")
    initial_question = llm.get_initial_question()
    print(f"\n🤖 AI: {initial_question}")
    
    total_latency = 0
    total_tokens = 0
    strategy_changes = []
    last_strategy = "continue"
    
    for turn in range(1, num_turns + 1):
        # 用户回复
        user_response = user.generate_response(initial_question)
        print(f"\n👤 User (Turn {turn}): {user_response}")
        
        # AI 回复
        result = llm.generate_response(user_response)
        ai_response = result["response"]
        rhythm = result["rhythm_analysis"]
        latency = result["latency"]
        tokens = result["tokens"]
        
        total_latency += latency
        total_tokens += tokens
        
        print(f"🤖 AI: {ai_response}")
        print(f"   📊 节奏: {rhythm['suggested_strategy']} | "
              f"连续短答: {rhythm['consecutive_short_count']} | "
              f"长度: {rhythm['last_response_length']}")
        print(f"   ⏱️ 延迟: {latency}s | 🎫 Tokens: {tokens}")
        
        # 检查策略变化
        current_strategy = rhythm["suggested_strategy"]
        if current_strategy != last_strategy:
            strategy_changes.append({
                "turn": turn,
                "from": last_strategy,
                "to": current_strategy
            })
            last_strategy = current_strategy
        
        # 如果有节奏引导，显示
        if result["rhythm_instruction"]:
            print(f"   💡 节奏引导: {result['rhythm_instruction'][:60]}...")
        
        initial_question = ai_response
    
    # 打印统计
    print("\n" + "="*70)
    print("                    测试统计")
    print("="*70)
    print(f"总轮次: {num_turns}")
    print(f"平均延迟: {total_latency/num_turns:.2f}s")
    print(f"总 Tokens: {total_tokens}")
    print(f"策略变化: {len(strategy_changes)} 次")
    
    if strategy_changes:
        print("\n策略变化详情:")
        for change in strategy_changes:
            print(f"  Turn {change['turn']}: {change['from']} → {change['to']}")
    
    print("\n" + "="*70)
    print("                    测试完成")
    print("="*70)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="真实 LLM 对话测试")
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        default="normal",
        choices=["short", "mixed", "verbose", "normal"],
        help="用户人设"
    )
    parser.add_argument(
        "--level", "-l",
        type=str,
        default="A2",
        help="CEFR 等级"
    )
    parser.add_argument(
        "--turns", "-t",
        type=int,
        default=5,
        help="对话轮次"
    )
    
    args = parser.parse_args()
    
    run_real_conversation(
        persona=args.scenario,
        cefr_level=args.level,
        num_turns=args.turns
    )
