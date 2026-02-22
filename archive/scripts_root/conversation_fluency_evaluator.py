"""
对话流畅度评估器 - 优化版本
分离"流畅度"和"话题管理"，聚焦语言表达与交互自然度
使用LLM判断相关性，提高准确性
"""
import re
import json
import time
from typing import Dict, List, Any
from services.llm import LLMServiceFactory


class ConversationFluencyEvaluator:
    """
    对话流畅度评估器
    
    评估维度：
    1. 语法与表达（语法错误、用词准确、句式自然）
    2. 上下文连贯（呼应前文信息）
    3. 回应相关性（回复与用户提问直接相关）
    4. 交互自然度（语气符合场景，无机械感）
    
    注意：话题跳跃不属于流畅度问题，属于"话题管理"指标
    """
    
    @staticmethod
    def evaluate_fluency(
        user_input: str,
        ai_response: str,
        conversation_history: List[Dict[str, Any]] = None,
        turn_number: int = 1
    ) -> Dict[str, Any]:
        """
        评估单轮对话的流畅度
        
        Returns:
            {
                "fluency_score": 1-5,
                "grammar_errors": [],
                "semantic_coherence": True/False,
                "response_relevance": True/False,
                "naturalness": True/False,
                "issues": [],
                "topic_management": "good"/"fair"/"poor"  # 独立指标
            }
        """
        result = {
            "fluency_score": 5,  # 默认满分
            "grammar_errors": [],
            "semantic_coherence": True,
            "response_relevance": True,
            "naturalness": True,
            "issues": [],
            "topic_management": "good"
        }
        
        # 1. 语法与表达检查
        grammar_issues = ConversationFluencyEvaluator._check_grammar(ai_response)
        if grammar_issues:
            result["grammar_errors"] = grammar_issues
            result["fluency_score"] = min(result["fluency_score"], 2)
            result["issues"].extend([f"语法错误: {issue}" for issue in grammar_issues])
        
        # 2. 回应相关性检查（使用LLM）
        relevance_start_time = time.time()
        relevance = ConversationFluencyEvaluator._check_relevance(user_input, ai_response, use_llm=True)
        relevance_time = time.time() - relevance_start_time
        
        if not relevance["relevant"]:
            result["response_relevance"] = False
            result["fluency_score"] = min(result["fluency_score"], 1)
            result["issues"].append(f"回应不相关: {relevance['reason']}")
        result["relevance_score"] = relevance.get("relevance_score", 100)
        result["relevance_evaluation_time"] = relevance_time  # 记录总相关性评估时间
        result["llm_evaluation_time"] = relevance.get("llm_evaluation_time", 0)  # 记录LLM调用时间（如果有）
        
        # 3. 上下文连贯性检查
        if conversation_history:
            coherence = ConversationFluencyEvaluator._check_coherence(
                conversation_history, ai_response
            )
            if not coherence["coherent"]:
                result["semantic_coherence"] = False
                result["fluency_score"] = min(result["fluency_score"], 3)
                # 上下文不连贯不是严重问题，只是降分，不标记为流畅度问题
        
        # 4. 交互自然度检查
        naturalness = ConversationFluencyEvaluator._check_naturalness(ai_response)
        if not naturalness["natural"]:
            result["naturalness"] = False
            result["fluency_score"] = min(result["fluency_score"], 3)
            result["issues"].append(f"表达生硬: {naturalness['reason']}")
        
        # 5. 话题管理（独立指标，不影响流畅度评分）
        topic_mgmt = ConversationFluencyEvaluator._evaluate_topic_management(
            user_input, ai_response, conversation_history
        )
        result["topic_management"] = topic_mgmt["level"]
        result["topic_management_reason"] = topic_mgmt["reason"]
        
        return result
    
    @staticmethod
    def _check_grammar(text: str) -> List[str]:
        """检查语法错误"""
        errors = []
        
        # 检查基本语法问题
        # 1. 主谓一致
        if re.search(r'\b(he|she|it)\s+\w+[^s]\s+\w+', text, re.IGNORECASE):
            # 简单检查，可能误报
            pass
        
        # 2. 时态一致性
        # 这里可以添加更复杂的检查
        
        # 3. 常见错误模式
        common_errors = [
            (r'\b(very much)\s+(very)', '重复使用very'),
            (r'\b(more better)', 'more better错误'),
            (r'\b(most best)', 'most best错误'),
        ]
        
        for pattern, error_type in common_errors:
            if re.search(pattern, text, re.IGNORECASE):
                errors.append(error_type)
        
        return errors
    
    @staticmethod
    def _check_relevance(user_input: str, ai_response: str, use_llm: bool = True) -> Dict[str, Any]:
        """
        检查回应相关性
        优先使用LLM判断，回退到规则判断
        """
        if use_llm:
            try:
                return ConversationFluencyEvaluator._check_relevance_with_llm(user_input, ai_response)
            except Exception as e:
                # LLM失败时回退到规则判断
                print(f"  ⚠️ LLM判断失败，使用规则判断: {e}")
                return ConversationFluencyEvaluator._check_relevance_with_rules(user_input, ai_response)
        else:
            return ConversationFluencyEvaluator._check_relevance_with_rules(user_input, ai_response)
    
    @staticmethod
    def _check_relevance_with_llm(user_input: str, ai_response: str) -> Dict[str, Any]:
        """使用LLM判断相关性"""
        prompt = f"""判断AI回复是否与用户输入相关。

用户输入: "{user_input}"

AI回复: "{ai_response}"

请判断AI回复是否与用户输入相关。考虑以下情况：
1. 如果用户提问，AI是否回答了问题或提出了相关问题？
2. 如果用户陈述，AI是否回应了用户的话题或引导了相关话题？
3. AI的回复是否在语义上与用户输入相关（即使没有共同关键词）？

请以JSON格式回复：
{{
    "relevant": true/false,
    "reason": "判断理由（中文）",
    "relevance_score": 0-100
}}"""

        try:
            # 记录LLM调用时间
            llm_start_time = time.time()
            
            # 使用LLM服务（使用默认模型，通常是qwen-plus或qwen-max）
            llm_service = LLMServiceFactory.create()
            result = llm_service.chat_completion_json(
                messages=[{"role": "user", "content": prompt}],
                model=None,  # 使用默认模型
                temperature=0.1
            )
            
            llm_time = time.time() - llm_start_time
            
            # 处理可能的错误响应
            if isinstance(result, dict) and "error" in result:
                raise Exception(result.get("error", "LLM返回错误"))
            
            return {
                "relevant": result.get("relevant", True),
                "reason": result.get("reason", "LLM判断"),
                "relevance_score": result.get("relevance_score", 100),
                "llm_evaluation_time": llm_time  # 记录LLM调用时间
            }
        except Exception as e:
            raise Exception(f"LLM判断失败: {e}")
    
    @staticmethod
    def _check_relevance_with_rules(user_input: str, ai_response: str) -> Dict[str, Any]:
        """使用规则判断相关性（回退方案）"""
        user_lower = user_input.lower()
        ai_lower = ai_response.lower()
        
        # 提取用户输入的关键词（更宽松）
        user_keywords = ConversationFluencyEvaluator._extract_keywords(user_input)
        ai_keywords = ConversationFluencyEvaluator._extract_keywords(ai_response)
        
        # 检查是否有共同关键词
        common_keywords = set(user_keywords) & set(ai_keywords)
        
        # 检查用户是否提问
        is_question = '?' in user_input or any(
            word in user_lower for word in ['what', 'how', 'why', 'when', 'where', 'can', 'do', 'tell', 'recommend']
        )
        
        # 更智能的相关性检查
        # 1. 检查是否有共同关键词（至少1个）
        if len(common_keywords) >= 1:
            return {"relevant": True, "reason": f"包含共同关键词: {list(common_keywords)[:3]}"}
        
        # 2. 检查语义相关性（即使没有共同关键词）
        # 例如：用户说"football"，AI说"sport"或"player"也算相关
        semantic_pairs = [
            ('football', ['sport', 'player', 'team', 'game']),
            ('movie', ['film', 'watch', 'cinema', 'story']),
            ('book', ['read', 'author', 'novel', 'story']),
            ('cook', ['food', 'dish', 'recipe', 'kitchen']),
            ('english', ['language', 'learn', 'speak', 'communicate']),
            ('job', ['work', 'career', 'company', 'professional']),
        ]
        
        for user_word, related_words in semantic_pairs:
            if user_word in user_lower:
                if any(word in ai_lower for word in related_words):
                    return {"relevant": True, "reason": f"语义相关: {user_word} -> {related_words[0]}"}
        
        # 3. 检查AI是否在提问（引导话题也算相关）
        if is_question:
            # 如果是问题，AI应该直接回答或提问相关的问题
            # 如果AI也在提问，检查问题是否相关
            ai_is_question = '?' in ai_response
            if ai_is_question:
                # AI提问也算相关（引导话题）
                return {"relevant": True, "reason": "AI提问引导话题"}
            else:
                # AI应该回答，检查是否包含问题相关的关键词
                if len(common_keywords) >= 1:
                    return {"relevant": True, "reason": "回答了问题"}
                else:
                    # 检查是否回答了问题的意图
                    # 例如：用户问"tell me more"，AI提供了更多信息
                    if any(word in ai_lower for word in ['sure', 'yes', 'okay', 'here', 'let']):
                        return {"relevant": True, "reason": "回应了问题意图"}
                    return {"relevant": False, "reason": "未回应问题关键词"}
        else:
            # 如果不是问题，AI应该回应话题或提问引导
            # 检查AI是否在引导话题（提问也算相关）
            if '?' in ai_response:
                return {"relevant": True, "reason": "AI提问引导话题"}
            # 检查是否有语义相关性
            if len(common_keywords) >= 1:
                return {"relevant": True, "reason": "回应了用户话题"}
            else:
                return {"relevant": False, "reason": "未回应用户话题"}
    
    @staticmethod
    def _check_coherence(conversation_history: List[Dict[str, Any]], ai_response: str) -> Dict[str, Any]:
        """检查上下文连贯性"""
        if not conversation_history or len(conversation_history) < 2:
            return {"coherent": True, "reason": "对话历史不足"}
        
        # 提取历史对话中的关键实体（人名、地名、主题等）
        history_text = " ".join([
            msg.get("content", "") for msg in conversation_history[-4:]  # 最近4条消息
        ])
        
        history_keywords = ConversationFluencyEvaluator._extract_keywords(history_text)
        ai_keywords = ConversationFluencyEvaluator._extract_keywords(ai_response)
        
        # 检查AI回复是否提及历史关键词
        common_keywords = set(history_keywords) & set(ai_keywords)
        
        if len(common_keywords) >= 1:
            return {"coherent": True, "reason": f"呼应前文: {list(common_keywords)[:3]}"}
        else:
            return {"coherent": False, "reason": "未呼应前文关键信息"}
    
    @staticmethod
    def _check_naturalness(text: str) -> Dict[str, Any]:
        """检查交互自然度"""
        # 检查是否有机械重复
        sentences = re.split(r'[.!?]', text)
        if len(sentences) > 1:
            # 检查是否有重复的句子开头
            first_words = [s.strip().split()[0].lower() if s.strip().split() else "" 
                          for s in sentences if s.strip()]
            if len(set(first_words)) < len(first_words) * 0.5:
                return {"natural": False, "reason": "句式重复"}
        
        # 检查是否有语气词（表示自然）
        has_tone_words = any(word in text.lower() for word in [
            'sounds', 'great', 'wonderful', 'interesting', 'amazing', 'exciting'
        ])
        
        # 检查是否过于正式（可能不自然）
        formal_words = ['therefore', 'furthermore', 'nevertheless', 'consequently']
        has_formal = any(word in text.lower() for word in formal_words)
        
        if has_formal and not has_tone_words:
            return {"natural": False, "reason": "语气过于正式"}
        
        return {"natural": True, "reason": "表达自然"}
    
    @staticmethod
    def _evaluate_topic_management(
        user_input: str,
        ai_response: str,
        conversation_history: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        评估话题管理（独立指标，不影响流畅度）
        
        Returns:
            {
                "level": "good"/"fair"/"poor",
                "reason": "说明"
            }
        """
        user_keywords = ConversationFluencyEvaluator._extract_keywords(user_input)
        ai_keywords = ConversationFluencyEvaluator._extract_keywords(ai_response)
        
        # 检查话题延续性
        common_keywords = set(user_keywords) & set(ai_keywords)
        
        if len(common_keywords) >= 2:
            return {"level": "good", "reason": "话题延续良好"}
        elif len(common_keywords) >= 1:
            return {"level": "fair", "reason": "话题部分延续"}
        else:
            return {"level": "poor", "reason": "话题跳跃"}
    
    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """提取关键词"""
        # 过滤常见停用词
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be',
            'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'should', 'could', 'may', 'might', 'can', 'this', 'that', 'these',
            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him',
            'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their',
            'very', 'really', 'quite', 'so', 'too', 'also', 'just', 'only'
        }
        
        # 提取4个字符以上的单词
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        keywords = [w for w in words if w not in stop_words]
        
        # 返回前10个关键词
        return keywords[:10]


def re_evaluate_conversations(results_file: str = "conversation_quality_results.json"):
    """重新评估所有对话的流畅度"""
    import json
    
    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    evaluator = ConversationFluencyEvaluator()
    re_evaluated_results = []
    
    for scenario in results:
        scenario_name = scenario['scenario']
        turns = scenario['turns']
        
        re_evaluated_turns = []
        conversation_history = []
        
        for turn in turns:
            user_input = turn['user_input']
            ai_response = turn['ai_response']
            
            # 重新评估流畅度
            fluency_result = evaluator.evaluate_fluency(
                user_input=user_input,
                ai_response=ai_response,
                conversation_history=conversation_history,
                turn_number=turn['turn']
            )
            
            # 更新对话历史
            conversation_history.append({
                "role": "user",
                "content": user_input
            })
            conversation_history.append({
                "role": "assistant",
                "content": ai_response
            })
            
            # 保存重新评估的结果
            re_evaluated_turn = turn.copy()
            re_evaluated_turn['fluency_evaluation'] = fluency_result
            re_evaluated_turns.append(re_evaluated_turn)
        
        re_evaluated_results.append({
            "scenario": scenario_name,
            "turns": re_evaluated_turns
        })
    
    # 保存重新评估的结果
    output_file = "conversation_fluency_re_evaluated.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(re_evaluated_results, f, ensure_ascii=False, indent=2)
    
    return re_evaluated_results


if __name__ == "__main__":
    re_evaluate_conversations()

