"""
GPT-4o Audio 服务 - 支持直接音频输入的LLM服务

使用 gpt-4o-audio-preview 模型，可以直接处理音频输入，
无需先转录为文本，减少延迟并保留语音中的细微差别。

支持流式输出，可以逐字返回响应，降低首字延迟。
"""
import base64
import json
import re
from typing import Optional, List, Dict, Any, AsyncGenerator, Generator
from openai import OpenAI
import httpx

from config.llm_config import llm_config
from services.utils.logger import get_logger

logger = get_logger("services.gpt4o_audio")


class GPT4oAudioService:
    """GPT-4o Audio 服务 - 直接处理音频输入"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-audio-preview"
    ):
        """
        初始化 GPT-4o Audio 服务
        
        Args:
            api_key: OpenAI API密钥
            base_url: API基础URL（如代理地址）
            model: 模型名称
        """
        self.api_key = api_key or llm_config.get_openai_api_key()
        self.base_url = base_url or llm_config.get_openai_base_url()
        self.model = model
        
        # 创建OpenAI客户端
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
            client_kwargs["http_client"] = httpx.Client(
                base_url=self.base_url,
                follow_redirects=True
            )
        
        self.client = OpenAI(**client_kwargs)
        logger.info(f"GPT-4o Audio服务初始化: model={model}, base_url={self.base_url}")
    
    def process_audio(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_text_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理音频输入，返回文本响应
        
        Args:
            audio_data: 音频数据（bytes）
            audio_format: 音频格式（wav, mp3, webm等）
            system_prompt: 系统提示词
            conversation_history: 对话历史
            user_text_prompt: 附加的用户文本提示（可选）
            
        Returns:
            {
                "response": str,  # 模型的文本响应
                "transcription": str,  # 音频转录（如果模型返回）
                "usage": dict  # token使用情况
            }
        """
        try:
            # 将音频编码为base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # 构建消息
            messages = []
            
            # 系统提示
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            else:
                messages.append({
                    "role": "system",
                    "content": self._get_default_system_prompt()
                })
            
            # 对话历史
            if conversation_history:
                messages.extend(conversation_history)
            
            # 用户消息（包含音频）
            user_content = []
            
            # 添加音频内容
            user_content.append({
                "type": "input_audio",
                "input_audio": {
                    "data": audio_base64,
                    "format": audio_format
                }
            })
            
            # 如果有附加文本提示
            if user_text_prompt:
                user_content.append({
                    "type": "text",
                    "text": user_text_prompt
                })
            
            messages.append({
                "role": "user",
                "content": user_content
            })
            
            logger.info(f"[process_audio] 发送音频到GPT-4o Audio, 大小: {len(audio_data)} bytes")
            
            # 调用API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            # 解析响应
            assistant_message = response.choices[0].message.content
            
            result = {
                "response": assistant_message,
                "transcription": None,  # GPT-4o Audio可能不直接返回转录
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
            logger.info(f"[process_audio] GPT-4o Audio响应: {assistant_message[:100]}...")
            
            return result
            
        except Exception as e:
            logger.error(f"[process_audio] GPT-4o Audio处理失败: {e}", exc_info=True)
            raise
    
    def process_audio_stream(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_text_prompt: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        流式处理音频输入，逐字返回响应
        
        Args:
            audio_data: 音频数据（bytes）
            audio_format: 音频格式
            system_prompt: 系统提示词
            conversation_history: 对话历史
            user_text_prompt: 附加的用户文本提示
            
        Yields:
            str: 响应文本片段
        """
        try:
            # 将音频编码为base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # 构建消息
            messages = []
            
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({"role": "system", "content": self._get_default_system_prompt()})
            
            if conversation_history:
                messages.extend(conversation_history)
            
            # 用户消息（包含音频）
            user_content = [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": audio_base64,
                        "format": audio_format
                    }
                }
            ]
            
            if user_text_prompt:
                user_content.append({"type": "text", "text": user_text_prompt})
            
            messages.append({"role": "user", "content": user_content})
            
            logger.info(f"[process_audio_stream] 流式请求GPT-4o Audio, 音频大小: {len(audio_data)} bytes")
            
            # 流式调用API
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=True  # 启用流式输出
            )
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    yield content
                    
        except Exception as e:
            logger.error(f"[process_audio_stream] 流式处理失败: {e}", exc_info=True)
            raise
    
    def process_audio_with_evaluation_stream(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式处理音频并进行评估，边生成边返回
        
        Yields:
            {"type": "chunk", "content": "..."} - 文本片段
            {"type": "complete", "data": {...}} - 完整解析结果
        """
        system_prompt = self._build_evaluation_prompt(user_profile)
        
        user_text_prompt = """请根据用户的语音回答：
1. 首先转录用户说的内容
2. 评估用户的英语水平（给出分数和CEFR等级）
3. 生成一个适合用户水平的后续问题

请按以下JSON格式返回：
{
    "transcription": "用户说的内容",
    "evaluation": {
        "overall_score": 0-100,
        "cefr_level": "A1/A2/B1/B2/C1/C2",
        "strengths": ["强项1", "强项2"],
        "weaknesses": ["弱项1", "弱项2"],
        "feedback": "简短反馈"
    },
    "next_question": "下一个问题（英文，附带中文翻译）"
}"""
        
        full_response = ""
        
        try:
            for chunk in self.process_audio_stream(
                audio_data=audio_data,
                audio_format=audio_format,
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                user_text_prompt=user_text_prompt
            ):
                full_response += chunk
                yield {"type": "chunk", "content": chunk}
            
            # 流式完成后，解析完整响应
            try:
                json_match = re.search(r'\{[\s\S]*\}', full_response)
                if json_match:
                    parsed = json.loads(json_match.group())
                    yield {
                        "type": "complete",
                        "data": {
                            "transcription": parsed.get("transcription", ""),
                            "evaluation": parsed.get("evaluation", {}),
                            "next_question": parsed.get("next_question", ""),
                            "response": full_response
                        }
                    }
                else:
                    yield {
                        "type": "complete",
                        "data": {
                            "transcription": "",
                            "evaluation": {"overall_score": 50, "cefr_level": "A2"},
                            "next_question": full_response,
                            "response": full_response
                        }
                    }
            except json.JSONDecodeError:
                yield {
                    "type": "complete",
                    "data": {
                        "transcription": "",
                        "evaluation": {"overall_score": 50, "cefr_level": "A2"},
                        "next_question": full_response,
                        "response": full_response
                    }
                }
                
        except Exception as e:
            logger.error(f"[process_audio_with_evaluation_stream] 流式处理失败: {e}")
            raise
    
    def process_audio_with_evaluation(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        处理音频并进行英语评估（一次调用完成转录+评估+生成问题）
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            conversation_history: 对话历史
            user_profile: 用户画像
            
        Returns:
            {
                "transcription": str,  # 用户说的内容（转录）
                "evaluation": dict,    # 评估结果
                "next_question": str,  # 下一个问题
                "response": str        # 完整响应
            }
        """
        # 构建专门的系统提示词，让模型一次性完成所有任务
        system_prompt = self._build_evaluation_prompt(user_profile)
        
        # 附加提示，要求模型返回结构化响应
        user_text_prompt = """请根据用户的语音回答：
1. 首先转录用户说的内容
2. 评估用户的英语水平（给出分数和CEFR等级）
3. 生成一个适合用户水平的后续问题

请按以下JSON格式返回：
{
    "transcription": "用户说的内容",
    "evaluation": {
        "overall_score": 0-100,
        "cefr_level": "A1/A2/B1/B2/C1/C2",
        "strengths": ["强项1", "强项2"],
        "weaknesses": ["弱项1", "弱项2"],
        "feedback": "简短反馈"
    },
    "next_question": "下一个问题（英文，附带中文翻译）"
}"""
        
        try:
            result = self.process_audio(
                audio_data=audio_data,
                audio_format=audio_format,
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                user_text_prompt=user_text_prompt
            )
            
            # 尝试解析JSON响应
            response_text = result["response"]
            
            try:
                # 提取JSON部分
                import re
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    parsed = json.loads(json_match.group())
                    return {
                        "transcription": parsed.get("transcription", ""),
                        "evaluation": parsed.get("evaluation", {}),
                        "next_question": parsed.get("next_question", ""),
                        "response": response_text,
                        "usage": result["usage"]
                    }
            except json.JSONDecodeError:
                pass
            
            # 如果解析失败，返回原始响应
            return {
                "transcription": "",
                "evaluation": {
                    "overall_score": 50,
                    "cefr_level": "A2",
                    "strengths": [],
                    "weaknesses": [],
                    "feedback": ""
                },
                "next_question": response_text,
                "response": response_text,
                "usage": result["usage"]
            }
            
        except Exception as e:
            logger.error(f"[process_audio_with_evaluation] 处理失败: {e}")
            raise
    
    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """You are an English language tutor helping students practice their spoken English.
Your role is to:
1. Listen carefully to the student's spoken response
2. Understand what they're trying to say, even if there are errors
3. Respond naturally and encouragingly
4. Ask follow-up questions to keep the conversation going
5. Adjust your language complexity to match the student's level

Be patient, supportive, and focus on communication rather than perfection."""
    
    def _build_evaluation_prompt(self, user_profile: Optional[Dict[str, Any]] = None) -> str:
        """构建评估用的系统提示词"""
        base_prompt = """You are an expert English language assessor and tutor.

Your tasks:
1. TRANSCRIBE: Listen to the audio and transcribe exactly what the user said
2. EVALUATE: Assess their English proficiency based on:
   - Vocabulary usage
   - Grammar accuracy
   - Pronunciation clarity (from audio)
   - Fluency and coherence
   - Content relevance
3. GENERATE: Create an appropriate follow-up question

Scoring guidelines:
- 0-20: Beginner (A1) - Very basic, many errors
- 21-40: Elementary (A2) - Simple sentences, frequent errors
- 41-60: Intermediate (B1) - Can communicate, some errors
- 61-80: Upper-Intermediate (B2) - Good communication, minor errors
- 81-90: Advanced (C1) - Fluent, rare errors
- 91-100: Proficient (C2) - Near-native level

Be encouraging but honest in your assessment."""
        
        if user_profile:
            base_prompt += f"""

Current user profile:
- Current level: {user_profile.get('cefr_level', 'Unknown')}
- Previous score: {user_profile.get('overall_score', 'Unknown')}
- Strengths: {user_profile.get('strengths', [])}
- Weaknesses: {user_profile.get('weaknesses', [])}

Adjust the difficulty of your next question based on this profile."""
        
        return base_prompt


# 工厂函数
def create_gpt4o_audio_service(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "gpt-4o-audio-preview"
) -> GPT4oAudioService:
    """创建GPT-4o Audio服务实例"""
    return GPT4oAudioService(
        api_key=api_key,
        base_url=base_url,
        model=model
    )

