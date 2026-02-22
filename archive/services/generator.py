"""
题目生成服务 - 基于能力画像生成适配题目
"""
from typing import List, Dict, Any, Optional
from services.llm import LLMService
from prompts.builders import PromptBuilder
from config.topics import TopicPool
from services.utils.logger import get_logger

logger = get_logger("services.generator")


class QuestionGeneratorService:
    """题目生成服务 - 负责生成适配的对话题目"""
    
    def __init__(
        self,
        llm_service: LLMService,
        prompt_builder: Optional[PromptBuilder] = None,
        topic_pool: Optional[TopicPool] = None
    ):
        self.llm_service = llm_service
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.topic_pool = topic_pool or TopicPool()

    def generate_question(
        self,
        ability_profile: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        previous_topics: Optional[List[str]] = None,
        user_interests: Optional[List[Dict[str, Any]]] = None,
        use_cache: bool = True
    ) -> str:
        """
        生成适配题目 - 基于难度和兴趣动态生成
        
        Args:
            ability_profile: 用户能力画像 (包含 cefr_level, overall_score, strengths, weaknesses)
            conversation_history: 对话历史（用于连贯性）
            previous_topics: 已讨论的主题列表
            user_interests: 用户兴趣列表 [{"category": "tech", "weight": 0.8, "tags": ["AI"]}, ...]
            use_cache: 是否使用缓存
            
        Returns:
            生成的题目文本
        """
        logger.info(f"[generate_question] INPUT: ability_profile={ability_profile}, interests={user_interests}")
        
        # 获取适配的主题池（作为备选参考）
        cefr_level = ability_profile.get("cefr_level", "A1")
        available_topics = self.topic_pool.get_topics_by_level(cefr_level)
        logger.debug(f"[generate_question] Available topics for {cefr_level}: {len(available_topics)} topics")
        
        # 构建生成提示词（包含对话历史和用户兴趣）
        messages = self.prompt_builder.build_generation_prompt(
            ability_profile=ability_profile,
            topic_pool=available_topics,
            conversation_history=conversation_history,
            previous_topics=previous_topics,
            user_interests=user_interests  # 🆕 传入用户兴趣
        )
        logger.debug(f"[generate_question] Built prompt with {len(messages)} messages, interests included: {bool(user_interests)}")
        
        # 调用LLM生成题目
        try:
            logger.debug(f"[generate_question] Calling LLM to generate question")
            question = self.llm_service.chat_completion(
                messages=messages,
                temperature=0.7
            )
            question = question.strip()
            logger.info(f"[generate_question] OUTPUT: Generated question: {question[:100]}...")
            return question
        except Exception as e:
            logger.error(f"[generate_question] Question generation failed: {e}")
            # 如果生成失败，返回默认题目
            default_question = self._create_default_question(cefr_level, str(e))
            logger.warning(f"[generate_question] Using default question")
            return default_question

    def _create_default_question(self, cefr_level: str, error_message: str) -> str:
        """创建默认题目（用于错误处理）"""
        default_questions = {
            "A1": "Can you tell me about your favorite food? (你能告诉我你最喜欢的食物吗？)",
            "A2": "What did you do last weekend? (你上周末做了什么？)",
            "B1": "How do you think technology has changed our daily life? (你认为科技如何改变了我们的日常生活？)",
            "B2": "What are your views on environmental protection? (你对环境保护有什么看法？)",
            "C1": "Discuss the impact of artificial intelligence on the job market. (讨论人工智能对就业市场的影响。)",
            "C2": "Analyze the relationship between economic development and cultural preservation. (分析经济发展与文化保护之间的关系。)"
        }
        return default_questions.get(cefr_level, default_questions["A1"])


