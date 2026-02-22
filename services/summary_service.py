"""
对话摘要生成服务

用于将长对话压缩为简短摘要，保留关键信息。
支持增量更新：新摘要可以与旧摘要合并。
"""

import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from config.settings import settings

logger = logging.getLogger(__name__)


# === 摘要生成 Prompt ===

SUMMARY_SYSTEM_PROMPT = """You are a conversation summarizer for an English learning app.
Your task is to create brief, useful summaries that help maintain conversation continuity.

Output rules:
- Write in English
- Be concise (under 80 words)
- Focus on actionable information for the AI tutor
- Use present tense for ongoing facts, past tense for events
- **CRITICAL**: Extract specific entities (names, places, specific hobbies)"""

SUMMARY_USER_PROMPT = """Summarize this conversation segment. Focus on:
1. **Key Facts**: Specific names, numbers, or preferences mentioned (e.g., "Cat's name: Luna", "Job: Engineer")
2. **Current Topic**: What exactly are they discussing right now?
3. **User State**: Current mood or learning challenge

Conversation:
{conversation}

{merge_instruction}

Output a brief summary (under 80 words). Start with "Key Facts:" if any specific details were mentioned."""

MERGE_INSTRUCTION = """Previous summary to incorporate:
{previous_summary}

Merge the new information with the previous summary, keeping the most relevant details."""


class SummaryService:
    """
    对话摘要服务
    
    使用 GPT-4o-mini 生成对话摘要，成本低且速度快。
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化摘要服务
        
        Args:
            api_key: OpenAI API Key（默认从 settings 读取）
            base_url: API Base URL（默认从 settings 读取）
        """
        self.client = AsyncOpenAI(
            api_key=api_key or settings.openai_official_api_key or settings.openai_api_key,
            base_url=base_url or settings.openai_official_base_url or "https://api.openai.com/v1"
        )
        self.model = "gpt-4o-mini"  # 使用便宜的模型生成摘要
        self.max_tokens = 150
        self.temperature = 0.3  # 低温度，更确定性
    
    async def generate_summary(
        self,
        messages: List[Dict[str, str]],
        existing_summary: str = ""
    ) -> str:
        """
        生成对话摘要
        
        Args:
            messages: 需要摘要的消息列表 [{"role": "user", "content": "..."}]
            existing_summary: 已有的摘要（用于增量更新）
        
        Returns:
            新的摘要文本
        """
        if not messages:
            return existing_summary
        
        # 构建对话文本
        conversation_lines = []
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            # 限制单条消息长度
            if len(content) > 300:
                content = content[:300] + "..."
            conversation_lines.append(f"{role}: {content}")
        
        conversation_text = "\n".join(conversation_lines)
        
        # 构建 merge 指令
        merge_instruction = ""
        if existing_summary:
            merge_instruction = MERGE_INSTRUCTION.format(previous_summary=existing_summary)
        
        user_prompt = SUMMARY_USER_PROMPT.format(
            conversation=conversation_text,
            merge_instruction=merge_instruction
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            summary = response.choices[0].message.content.strip()
            logger.info(f"[SummaryService] Generated summary: {summary[:50]}...")
            return summary
            
        except Exception as e:
            logger.error(f"[SummaryService] Summary generation failed: {e}")
            # 失败时保留原摘要
            return existing_summary
    
    async def extract_key_facts(
        self,
        messages: List[Dict[str, str]]
    ) -> List[str]:
        """
        从对话中提取关键事实
        
        Args:
            messages: 消息列表
            
        Returns:
            关键事实列表
        """
        if not messages:
            return []
        
        conversation_lines = []
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")[:200]
            conversation_lines.append(f"{role}: {content}")
        
        conversation_text = "\n".join(conversation_lines)
        
        prompt = f"""Extract key facts about the user from this conversation.
Focus on: interests, background, preferences, learning goals.

Conversation:
{conversation_text}

Output as a JSON array of strings, max 5 facts:
["fact1", "fact2", ...]"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            if isinstance(result, list):
                return result[:5]
            elif isinstance(result, dict) and "facts" in result:
                return result["facts"][:5]
            else:
                return []
                
        except Exception as e:
            logger.error(f"[SummaryService] Key facts extraction failed: {e}")
            return []


# === 单例实例 ===

_summary_service: Optional[SummaryService] = None


def get_summary_service() -> SummaryService:
    """获取摘要服务单例"""
    global _summary_service
    if _summary_service is None:
        _summary_service = SummaryService()
    return _summary_service


async def generate_conversation_summary(
    messages: List[Dict[str, str]],
    existing_summary: str = ""
) -> str:
    """
    便捷函数：生成对话摘要
    
    Args:
        messages: 消息列表
        existing_summary: 已有摘要
        
    Returns:
        新摘要
    """
    service = get_summary_service()
    return await service.generate_summary(messages, existing_summary)
