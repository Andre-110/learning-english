"""
用户模拟器 - 模拟不同等级英语学习者的回复

用于：
- AI-to-AI 对话测试
- 系统压力测试
- Prompt 效果验证
"""

from typing import Optional, Dict, Any, List
from services.llm import call_llm
from services.utils.logger import get_logger

logger = get_logger("services.user_simulator")


# CEFR 等级对应的语言能力描述
LEVEL_DESCRIPTIONS = {
    'A1': 'very basic vocabulary, simple sentences, frequent grammar mistakes, may mix Chinese words',
    'A2': 'limited vocabulary, simple sentences, some grammar errors, occasional Chinese words',
    'B1': 'moderate vocabulary, compound sentences, occasional errors, mostly fluent',
    'B2': 'good vocabulary, complex sentences, few errors, fluent expression',
    'C1': 'advanced vocabulary, sophisticated sentences, rare errors, natural expression',
    'C2': 'near-native vocabulary, elegant sentences, essentially error-free'
}


class UserSimulator:
    """
    模拟不同等级英语学习者的回复
    """
    
    def __init__(self, level: str = 'A2'):
        """
        Args:
            level: CEFR 等级 (A1-C2)
        """
        self.level = level
        self.ability = LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS['A2'])
    
    def respond(
        self,
        ai_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        根据 AI 的问题生成用户回复
        
        Args:
            ai_message: AI（教练）的消息
            conversation_history: 对话历史
            
        Returns:
            模拟用户的回复
        """
        # 构建对话上下文
        context = ""
        if conversation_history:
            recent = conversation_history[-4:]
            for msg in recent:
                role = "Tutor" if msg.get('role') == 'assistant' else "You"
                content = msg.get('content', '')[:100]
                context += f"{role}: {content}\n"
        
        prompt = f'''You are an English learner at {self.level} level practicing with a tutor.
Your language ability: {self.ability}

Previous conversation:
{context}

The tutor just said: "{ai_message}"

Respond naturally as a real learner would. Sometimes give short answers, sometimes longer ones.
Be authentic - include hesitations, self-corrections, or uncertainty when appropriate for your level.

Your response (no quotes, just the response):'''

        try:
            response = call_llm(
                system_prompt="You are simulating an English learner. Respond in character.",
                user_prompt=prompt,
                max_tokens=150,
                temperature=0.8
            )
            return response.strip()
        except Exception as e:
            logger.error(f"模拟用户回复失败: {e}")
            return "I'm not sure what to say."


def create_user_simulator(level: str = 'A2') -> UserSimulator:
    """创建用户模拟器"""
    return UserSimulator(level)
