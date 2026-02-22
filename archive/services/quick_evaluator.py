"""
快速评估服务 - 基于LLM prompt的快速评估（<500ms）
"""
from typing import Dict, Any, Optional, List
import json
from services.llm import LLMService
from prompts.builders import PromptBuilder
from services.utils.logger import get_logger

logger = get_logger("services.quick_evaluator")


class QuickEvaluatorService:
    """快速评估服务 - 使用LLM prompt进行快速评估，不阻塞主流程"""
    
    def __init__(self, llm_service: Optional[LLMService] = None, prompt_builder: Optional[PromptBuilder] = None):
        """
        初始化快速评估服务
        
        Args:
            llm_service: LLM服务实例
            prompt_builder: 提示词构建器
        """
        self.llm_service = llm_service
        self.prompt_builder = prompt_builder or PromptBuilder()
    
    def quick_evaluate(
        self,
        user_response: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        previous_assessment: Optional[Dict[str, Any]] = None,
        conversation_length: int = 0,
        use_llm: bool = False  # 默认使用规则评估（更快）
    ) -> Dict[str, Any]:
        """
        快速评估用户回答（默认使用规则评估，可选LLM）
        
        Args:
            user_response: 用户回答文本
            conversation_history: 对话历史（可选）
            previous_assessment: 上一次评估结果（可选）
            conversation_length: 对话长度（轮数）
            use_llm: 是否使用LLM评估（默认False，使用规则评估更快）
            
        Returns:
            快速评估结果字典
        """
        # 默认使用规则评估（<10ms），避免LLM调用延迟
        if not use_llm:
            return self._rule_based_evaluate(user_response, previous_assessment)
        
        logger.debug(f"[quick_evaluate] 快速评估（LLM）: response_length={len(user_response)}")
        
        if not self.llm_service:
            logger.warning("[quick_evaluate] LLM服务未初始化，返回规则评估")
            return self._rule_based_evaluate(user_response, previous_assessment)
        
        try:
            # 构建快速评估提示词
            from prompts.templates import QuickEvaluationPrompt
            quick_eval_prompt = QuickEvaluationPrompt()
            
            prompt_text = quick_eval_prompt.render(
                user_response=user_response,
                conversation_history=conversation_history,
                previous_assessment=previous_assessment
            )
            
            # 调用LLM进行快速评估
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的英语评估专家。请快速、准确地评估用户的英语水平，并返回JSON格式的结果。"
                },
                {
                    "role": "user",
                    "content": prompt_text
                }
            ]
            
            # 使用较低temperature以获得更稳定的结果
            response = self.llm_service.chat_completion(
                messages=messages,
                temperature=0.3  # 较低温度，更稳定
            )
            
            # 解析JSON响应
            result = self._parse_llm_response(response)
            
            logger.debug(f"[quick_evaluate] LLM快速评估结果: score={result.get('overall_score')}, level={result.get('cefr_level')}")
            
            return result
            
        except Exception as e:
            logger.error(f"[quick_evaluate] LLM快速评估失败: {e}", exc_info=True)
            # 如果LLM调用失败，返回规则评估
            return self._rule_based_evaluate(user_response, previous_assessment)
    
    def _rule_based_evaluate(
        self,
        user_response: str,
        previous_assessment: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        基于规则的快速评估（<10ms，无LLM调用）
        
        用于快速响应，详细评估由异步完整评估完成
        """
        import re
        
        # 基础分数（基于文本长度和复杂度）
        words = user_response.split()
        word_count = len(words)
        char_count = len(user_response)
        
        # 词汇复杂度（平均词长）
        avg_word_length = char_count / max(word_count, 1)
        
        # 句子数量
        sentences = re.split(r'[.!?。！？]', user_response)
        sentence_count = len([s for s in sentences if s.strip()])
        
        # 计算基础分数
        base_score = 30  # 基础分
        
        # 长度加分（最多+20分）
        length_bonus = min(word_count * 2, 20)
        
        # 复杂度加分（最多+15分）
        complexity_bonus = min((avg_word_length - 3) * 5, 15) if avg_word_length > 3 else 0
        
        # 句子结构加分（最多+15分）
        structure_bonus = min(sentence_count * 5, 15)
        
        # 使用前一次评估作为参考（平滑变化）
        if previous_assessment:
            prev_score = previous_assessment.get("overall_score", 50)
            raw_score = base_score + length_bonus + complexity_bonus + structure_bonus
            # 平滑处理：新分数 = 0.7 * 当前 + 0.3 * 前一次
            score = raw_score * 0.7 + prev_score * 0.3
        else:
            score = base_score + length_bonus + complexity_bonus + structure_bonus
        
        # 限制分数范围
        score = max(10, min(90, score))
        
        # 确定CEFR等级
        if score >= 80:
            cefr_level = "C1"
        elif score >= 65:
            cefr_level = "B2"
        elif score >= 50:
            cefr_level = "B1"
        elif score >= 35:
            cefr_level = "A2"
        else:
            cefr_level = "A1"
        
        # 简单的强弱项分析
        strengths = []
        weaknesses = []
        
        if word_count >= 10:
            strengths.append("回答较为完整")
        else:
            weaknesses.append("回答较短")
        
        if sentence_count >= 2:
            strengths.append("句子结构多样")
        else:
            weaknesses.append("句子结构单一")
        
        if avg_word_length >= 4:
            strengths.append("词汇使用较好")
        else:
            weaknesses.append("词汇较简单")
        
        return {
            "overall_score": round(score, 1),
            "cefr_level": cefr_level,
            "strengths": strengths if strengths else ["尝试回答问题"],
            "weaknesses": weaknesses if weaknesses else ["需要更多练习"],
            "confidence": 0.6,  # 规则评估置信度较低
            "is_rule_based": True  # 标记为规则评估
        }
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        解析LLM返回的JSON响应
        
        Args:
            response: LLM返回的文本
            
        Returns:
            解析后的评估结果字典
        """
        try:
            # 尝试提取JSON（可能包含markdown代码块）
            response = response.strip()
            
            # 移除可能的markdown代码块标记
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            # 解析JSON
            result = json.loads(response)
            
            # 验证和标准化结果
            return {
                "overall_score": float(result.get("overall_score", 50)),
                "cefr_level": str(result.get("cefr_level", "A1")).upper(),
                "strengths": list(result.get("strengths", [])),
                "weaknesses": list(result.get("weaknesses", [])),
                "confidence": float(result.get("confidence", 0.7))
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"[_parse_llm_response] JSON解析失败: {e}, response: {response[:200]}")
            # 尝试从文本中提取关键信息
            return self._extract_from_text(response)
        except Exception as e:
            logger.error(f"[_parse_llm_response] 解析失败: {e}")
            return self._default_assessment("")
    
    def _extract_from_text(self, text: str) -> Dict[str, Any]:
        """从文本中提取评估信息（备用方法，仅当JSON解析失败时使用）"""
        import re
        
        # 尝试提取分数
        score_match = re.search(r'(?:score|分数)[:\s]*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
        score = float(score_match.group(1)) if score_match else 50
        
        # 尝试提取CEFR等级
        level_match = re.search(r'(A[12]|B[12]|C[12])', text, re.IGNORECASE)
        level = level_match.group(1).upper() if level_match else "A1"
        
        return {
            "overall_score": min(100, max(0, score)),
            "cefr_level": level,
            "strengths": ["基础表达能力"],
            "weaknesses": ["需要更多评估数据"],
            "confidence": 0.6
        }
    
    def _default_assessment(self, user_response: str) -> Dict[str, Any]:
        """默认评估结果（当LLM调用失败时使用，仅作为fallback）"""
        length = len(user_response.strip())
        
        # 基于长度的简单估算（仅作为最后的fallback）
        if length < 10:
            score = 30
            level = "A1"
        elif length < 30:
            score = 50
            level = "A2"
        elif length < 60:
            score = 65
            level = "B1"
        else:
            score = 75
            level = "B2"
        
        return {
            "overall_score": float(score),
            "cefr_level": level,
            "strengths": ["基础表达能力"],
            "weaknesses": ["需要更详细的评估"],
            "confidence": 0.5  # 低置信度
        }




