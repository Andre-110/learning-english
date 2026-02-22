"""
对话管理器 - 管理对话流程和状态
"""
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
import uuid
from models.conversation import Conversation, Message, MessageRole, ConversationState
from models.user import UserProfile
from models.assessment import AssessmentResult
from services.evaluator import EvaluatorService
from services.generator import QuestionGeneratorService
from services.context import ContextManagerService
from services.report import ReportService
from services.interest_extractor import InterestExtractorService
from services.template_service import TemplateService
from services.quick_evaluator import QuickEvaluatorService
from services.async_evaluator import AsyncEvaluatorService
from storage.repository import ConversationRepository, UserRepository
from services.utils.logger import get_logger
from services.llm import LLMProvider

logger = get_logger("core.conversation")


class ConversationManager:
    """对话管理器 - 协调整个对话流程"""
    
    def __init__(
        self,
        evaluator_service: EvaluatorService,
        generator_service: QuestionGeneratorService,
        context_service: ContextManagerService,
        conversation_repo: ConversationRepository,
        user_repo: UserRepository,
        report_service: Optional[ReportService] = None,
        interest_extractor: Optional[InterestExtractorService] = None,
        template_service: Optional[TemplateService] = None,
        quick_evaluator: Optional[QuickEvaluatorService] = None,
        async_evaluator: Optional[AsyncEvaluatorService] = None
    ):
        self.evaluator_service = evaluator_service
        self.generator_service = generator_service
        self.context_service = context_service
        self.conversation_repo = conversation_repo
        self.user_repo = user_repo
        self.report_service = report_service
        self.interest_extractor = interest_extractor
        self.template_service = template_service
        self.quick_evaluator = quick_evaluator or QuickEvaluatorService()
        self.async_evaluator = async_evaluator

    def start_conversation(self, user_id: str) -> Conversation:
        """开始新对话"""
        logger.info(f"[start_conversation] INPUT: user_id={user_id}")
        
        conversation_id = str(uuid.uuid4())
        conversation = Conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            state=ConversationState.INITIALIZING
        )
        
        # 获取或创建用户画像
        user_profile = self.user_repo.get_or_create(user_id)
        logger.debug(f"[start_conversation] User profile: {user_profile.dict()}")
        
        # 构建能力画像
        ability_profile = {
            "cefr_level": user_profile.cefr_level.value,
            "overall_score": user_profile.overall_score,
            "strengths": user_profile.strengths,
            "weaknesses": user_profile.weaknesses
        }
        
        # 将用户兴趣转换为字典格式（用于传给生成器）
        user_interests = None
        if user_profile.interests:
            user_interests = [
                {
                    "category": interest.category, 
                    "weight": interest.weight,
                    "tags": interest.tags if hasattr(interest, 'tags') else []
                }
                for interest in user_profile.interests
            ]
            logger.info(f"[start_conversation] User interests: {[i['category'] for i in user_interests]}")
        
        # 🆕 统一使用生成器 - 同时考虑难度和兴趣
        initial_question = self.generator_service.generate_question(
            ability_profile=ability_profile,
            user_interests=user_interests  # 传入兴趣，让LLM动态生成
        )
        logger.info(f"[start_conversation] Generated initial question: {initial_question[:100]}...")
        
        # 添加系统消息和初始问题
        conversation.add_message(MessageRole.SYSTEM, "Welcome to LinguaCoach! Let's start our conversation.")
        conversation.add_message(MessageRole.ASSISTANT, initial_question)
        conversation.state = ConversationState.IN_PROGRESS
        
        # 保存对话
        self.conversation_repo.save(conversation)
        
        logger.info(f"[start_conversation] OUTPUT: conversation_id={conversation_id}, state={conversation.state}")
        return conversation

    def process_user_response(
        self,
        conversation_id: str,
        user_response: str
    ) -> Tuple[Conversation, AssessmentResult, str]:
        """
        处理用户回答
        
        Returns:
            (更新后的对话, 评估结果, 下一题)
        """
        logger.info(f"[process_user_response] INPUT: conversation_id={conversation_id}, user_response={user_response[:100]}...")
        
        # 获取对话
        conversation = self.conversation_repo.get(conversation_id)
        if not conversation:
            logger.error(f"[process_user_response] Conversation {conversation_id} not found")
            raise ValueError(f"Conversation {conversation_id} not found")
        
        logger.debug(f"[process_user_response] Conversation state: {conversation.state}, round_count: {len([m for m in conversation.messages if m.role == MessageRole.USER])}")
        
        # 添加用户消息
        conversation.add_message(MessageRole.USER, user_response)
        logger.debug(f"[process_user_response] Added user message")
        
        # 🆕 检测用户是否在问问题，如果是，先回答
        user_response_lower = user_response.lower().strip()
        is_question = self._is_user_asking_question(user_response_lower)
        assistant_response = None
        
        if is_question:
            logger.info(f"[process_user_response] User is asking a question: {user_response[:50]}...")
            # 生成回答
            assistant_response = self._generate_answer_to_question(
                user_response=user_response,
                conversation=conversation
            )
            if assistant_response:
                conversation.add_message(MessageRole.ASSISTANT, assistant_response)
                logger.info(f"[process_user_response] Generated answer: {assistant_response[:100]}...")
        
        # 获取上下文消息（包含摘要）
        context_messages = self.context_service.get_context_messages(
            conversation.messages,
            conversation.summary,
            conversation.summary_round
        )
        logger.debug(f"[process_user_response] Context messages count: {len(context_messages)}")
        
        # 执行评估
        round_number = len([m for m in conversation.messages if m.role == MessageRole.USER])
        logger.info(f"[process_user_response] Starting evaluation for round {round_number}")
        
        # 提取历史评估记录
        previous_assessments = []
        for msg in conversation.messages:
            if msg.metadata and "assessment" in msg.metadata:
                assess_data = msg.metadata["assessment"]
                if isinstance(assess_data, dict):
                    previous_assessments.append({
                        "round": assess_data.get("round_number", 0),
                        "overall_score": assess_data.get("ability_profile", {}).get("overall_score", 0),
                        "cefr_level": assess_data.get("ability_profile", {}).get("cefr_level", "A1"),
                        "strengths": assess_data.get("ability_profile", {}).get("strengths", []),
                        "weaknesses": assess_data.get("ability_profile", {}).get("weaknesses", [])
                    })
        
        assessment_result = self.evaluator_service.evaluate(
            conversation_messages=context_messages,
            current_response=user_response,
            round_number=round_number,
            previous_assessments=previous_assessments
        )
        
        logger.info(f"[process_user_response] Evaluation completed: score={assessment_result.ability_profile.overall_score}, level={assessment_result.ability_profile.cefr_level.value}")
        logger.debug(f"[process_user_response] Assessment details: {assessment_result.dict()}")
        
        # 在消息中保存评估结果元数据
        conversation.messages[-1].metadata["assessment"] = assessment_result.dict()
        
        # 提取对话历史（用于兴趣提取和问题生成）
        conversation_history_dict = [
            {"role": msg.role.value, "content": msg.content}
            for msg in context_messages[-6:]  # 最近3轮对话
        ]
        
        # 更新用户画像
        user_profile = self.user_repo.get(conversation.user_id)
        if user_profile:
            old_score = user_profile.overall_score
            old_level = user_profile.cefr_level.value
            user_profile.update_from_assessment(assessment_result)
            
            # 提取并更新用户兴趣
            if self.interest_extractor:
                try:
                    # 收集所有用户回答
                    user_responses = [
                        msg.content for msg in conversation.messages 
                        if msg.role == MessageRole.USER
                    ]
                    
                    if user_responses:
                        # 提取兴趣
                        new_interests = self.interest_extractor.extract_interests_from_conversation(
                            conversation_messages=conversation_history_dict,
                            user_responses=user_responses
                        )
                        
                        # 更新用户兴趣
                        if new_interests:
                            user_profile.interests = self.interest_extractor.update_user_interests(
                                current_interests=user_profile.interests,
                                new_interests=new_interests
                            )
                            logger.info(f"[process_user_response] Updated user interests: {len(user_profile.interests)} categories")
                except Exception as e:
                    logger.warning(f"[process_user_response] Interest extraction failed: {e}")
            
            self.user_repo.save(user_profile)
            logger.info(f"[process_user_response] User profile updated: {old_score:.1f}->{user_profile.overall_score:.1f}, {old_level}->{user_profile.cefr_level.value}")
        
        # 检查是否需要生成摘要
        if self.context_service.should_summarize(round_number):
            logger.info(f"[process_user_response] Creating summary for round {round_number}")
            summary = self.context_service.create_summary(
                conversation_messages=conversation.messages[:conversation.summary_round or len(conversation.messages)],
                current_round=round_number
            )
            conversation.summary = summary
            conversation.summary_round = round_number
            logger.debug(f"[process_user_response] Summary created: {summary[:100]}...")
        
        # 生成下一题（包含对话历史以保持连贯性）
        ability_profile = {
            "cefr_level": assessment_result.ability_profile.cefr_level.value,
            "overall_score": assessment_result.ability_profile.overall_score,
            "strengths": assessment_result.ability_profile.strengths,
            "weaknesses": assessment_result.ability_profile.weaknesses
        }
        logger.debug(f"[process_user_response] Generating next question with ability_profile: {ability_profile}")
        
        # 对话历史已在上面提取，这里不需要重复提取
        
        # 提取已讨论的主题（从assistant消息中提取）
        previous_topics = []
        discussed_categories = set()
        for msg in conversation.messages:
            if msg.role == MessageRole.ASSISTANT:
                # 简单提取主题关键词（可以从消息内容中提取）
                content_lower = msg.content.lower()
                if "daily life" in content_lower or "morning" in content_lower:
                    previous_topics.append("daily life")
                elif "healthy" in content_lower or "fitness" in content_lower:
                    previous_topics.append("healthy living")
                elif "environment" in content_lower or "green" in content_lower or "eco" in content_lower:
                    previous_topics.append("environment")
        
        # 🆕 统一使用生成器 - 同时考虑难度和兴趣
        # 将用户兴趣转换为字典格式
        user_interests = None
        if user_profile.interests:
            user_interests = [
                {
                    "category": interest.category, 
                    "weight": interest.weight,
                    "tags": interest.tags if hasattr(interest, 'tags') else []
                }
                for interest in user_profile.interests
            ]
        
        # 使用生成器动态生成问题（基于难度+兴趣+对话历史）
        next_question = self.generator_service.generate_question(
            ability_profile=ability_profile,
            conversation_history=conversation_history_dict,
            previous_topics=previous_topics,
            user_interests=user_interests  # 传入兴趣，让LLM动态生成
        )
        logger.info(f"[process_user_response] Generated next question (interests: {bool(user_interests)}): {next_question[:100]}...")
        
        conversation.add_message(MessageRole.ASSISTANT, next_question)
        
        # 保存对话
        self.conversation_repo.save(conversation)
        
        logger.info(f"[process_user_response] OUTPUT: round={round_number}, score={assessment_result.ability_profile.overall_score}, level={assessment_result.ability_profile.cefr_level.value}")
        
        # 🆕 如果用户问了问题，返回回答+新问题，否则只返回新问题
        if assistant_response:
            combined_response = f"{assistant_response}\n\n{next_question}"
            return conversation, assessment_result, combined_response
        
        return conversation, assessment_result, next_question
    
    def process_user_response_quick(
        self,
        conversation_id: str,
        user_response: str
    ) -> Tuple[Conversation, Dict[str, Any], str]:
        """
        快速处理用户回答（使用快速评估，不阻塞）
        
        Returns:
            (更新后的对话, 快速评估结果字典, 下一题)
        """
        logger.info(f"[process_user_response_quick] INPUT: conversation_id={conversation_id}, user_response={user_response[:100]}...")
        
        # 获取对话
        conversation = self.conversation_repo.get(conversation_id)
        if not conversation:
            logger.error(f"[process_user_response_quick] Conversation {conversation_id} not found")
            raise ValueError(f"Conversation {conversation_id} not found")
        
        # 添加用户消息
        conversation.add_message(MessageRole.USER, user_response)
        
        # 🆕 检测用户是否在问问题，如果是，先回答
        user_response_lower = user_response.lower().strip()
        is_question = self._is_user_asking_question(user_response_lower)
        assistant_response = None
        
        if is_question:
            logger.info(f"[process_user_response_quick] User is asking a question: {user_response[:50]}...")
            assistant_response = self._generate_answer_to_question(
                user_response=user_response,
                conversation=conversation
            )
            if assistant_response:
                conversation.add_message(MessageRole.ASSISTANT, assistant_response)
        
        # 获取上下文消息
        context_messages = self.context_service.get_context_messages(
            conversation.messages,
            conversation.summary,
            conversation.summary_round
        )
        
        # 提取对话历史（用于快速评估）
        conversation_history_dict = [
            {"role": msg.role.value, "content": msg.content}
            for msg in context_messages[-6:]  # 最近3轮对话
        ]
        
        # 获取上一次评估结果（用于快速评估的趋势分析）
        previous_assessment = None
        for msg in reversed(conversation.messages):
            if msg.metadata and "assessment" in msg.metadata:
                previous_assessment = msg.metadata["assessment"]
                break
        
        # 快速评估（<500ms，使用LLM prompt）
        round_number = len([m for m in conversation.messages if m.role == MessageRole.USER])
        quick_assessment = self.quick_evaluator.quick_evaluate(
            user_response=user_response,
            conversation_history=conversation_history_dict,  # 传入对话历史
            previous_assessment=previous_assessment,
            conversation_length=round_number
        )
        
        logger.info(f"[process_user_response_quick] Quick assessment: score={quick_assessment['overall_score']}, level={quick_assessment['cefr_level']}")
        
        # 获取用户画像（用于生成问题）
        user_profile = self.user_repo.get(conversation.user_id)
        
        # 生成下一题（使用快速评估结果）
        ability_profile = {
            "cefr_level": quick_assessment["cefr_level"],
            "overall_score": quick_assessment["overall_score"],
            "strengths": quick_assessment.get("strengths", []),
            "weaknesses": quick_assessment.get("weaknesses", [])
        }
        
        # 对话历史已在上面提取，这里不需要重复提取
        
        # 提取已讨论的主题
        previous_topics = []
        for msg in conversation.messages:
            if msg.role == MessageRole.ASSISTANT:
                content_lower = msg.content.lower()
                if "daily life" in content_lower or "morning" in content_lower:
                    previous_topics.append("daily life")
                elif "healthy" in content_lower or "fitness" in content_lower:
                    previous_topics.append("healthy living")
                elif "environment" in content_lower or "green" in content_lower:
                    previous_topics.append("environment")
        
        # 用户兴趣
        user_interests = None
        if user_profile and user_profile.interests:
            user_interests = [
                {
                    "category": interest.category,
                    "weight": interest.weight,
                    "tags": interest.tags if hasattr(interest, 'tags') else []
                }
                for interest in user_profile.interests
            ]
        
        # 生成问题
        next_question = self.generator_service.generate_question(
            ability_profile=ability_profile,
            conversation_history=conversation_history_dict,
            previous_topics=previous_topics,
            user_interests=user_interests
        )
        
        conversation.add_message(MessageRole.ASSISTANT, next_question)
        
        # 保存对话
        self.conversation_repo.save(conversation)
        
        # 如果用户问了问题，返回回答+新问题
        if assistant_response:
            combined_response = f"{assistant_response}\n\n{next_question}"
            return conversation, quick_assessment, combined_response
        
        return conversation, quick_assessment, next_question
    
    def _is_user_asking_question(self, user_response: str) -> bool:
        """
        检测用户是否在问问题或想换话题
        
        Args:
            user_response: 用户输入（已转为小写）
            
        Returns:
            是否是问题或话题切换请求
        """
        # 检测常见的问题模式
        question_patterns = [
            "who are you", "你是谁", "what are you", "你是什么",
            "what is", "what's", "what do", "what does",
            "how are", "how do", "how does", "how can",
            "why", "why do", "why does",
            "where", "where is", "where are",
            "when", "when do", "when does",
            "can you", "could you", "would you",
            "tell me", "explain", "describe",
            "？", "?", "吗", "呢"
        ]
        
        # 🆕 检测话题切换/想了解助手的模式
        topic_switch_patterns = [
            "let's talk about", "let us talk about", "i want to talk about",
            "i'd like to know", "i would like to know", "i want to know",
            "what about you", "how about you", "and you",
            "your favorite", "your opinion", "do you like", "do you think",
            "can we talk about", "let's discuss", "change topic",
            "something else", "different topic", "another topic",
            "tell me about yourself", "about you", "你呢", "你喜欢"
        ]
        
        # 检查是否包含问题模式
        for pattern in question_patterns:
            if pattern in user_response:
                return True
        
        # 🆕 检查是否包含话题切换模式
        for pattern in topic_switch_patterns:
            if pattern in user_response:
                logger.info(f"[_is_user_asking_question] Detected topic switch pattern: {pattern}")
                return True
        
        # 检查是否以疑问词开头
        question_starters = ["who", "what", "when", "where", "why", "how", "can", "could", "would", "do", "does", "did", "is", "are", "was", "were"]
        words = user_response.split()
        if words and words[0].lower() in question_starters:
            return True
        
        return False
    
    def _generate_answer_to_question(
        self,
        user_response: str,
        conversation: Conversation
    ) -> Optional[str]:
        """
        生成对用户问题的回答
        
        Args:
            user_response: 用户的问题
            conversation: 当前对话
            
        Returns:
            回答文本，如果无法回答则返回None
        """
        try:
            from services.llm import LLMServiceFactory
            from config.llm_config import llm_config
            
            # 创建LLM服务
            provider_name = llm_config.get_provider()
            provider = LLMProvider(provider_name)
            llm_service = LLMServiceFactory.create(provider=provider)
            
            # 构建回答提示词
            system_prompt = """You are LinguaCoach, an English learning assistant. 
When users ask you questions, answer them naturally and briefly in English (with Chinese translation if needed).
Then naturally transition to continue the English learning conversation."""
            
            # 获取对话上下文
            recent_messages = conversation.messages[-4:] if len(conversation.messages) > 4 else conversation.messages
            context = "\n".join([f"{msg.role.value}: {msg.content}" for msg in recent_messages])
            
            user_question = user_response
            
            prompt = f"""Context:
{context}

User's question: {user_question}

Please answer the user's question naturally and briefly in English. If the question is in Chinese, provide both English and Chinese responses.
Keep your answer concise (1-2 sentences)."""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            answer = llm_service.chat_completion(messages=messages, temperature=0.7)
            return answer.strip() if answer else None
            
        except Exception as e:
            logger.warning(f"[_generate_answer_to_question] Failed to generate answer: {e}")
            # 返回默认回答
            if "who are you" in user_response.lower() or "你是谁" in user_response:
                return "I'm LinguaCoach, your English learning assistant. I help you practice English through conversations and provide feedback on your speaking skills."
            return None

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话"""
        return self.conversation_repo.get(conversation_id)

    def get_user_conversations(self, user_id: str) -> List[Conversation]:
        """获取用户的所有对话"""
        return self.conversation_repo.get_by_user(user_id)

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        return self.user_repo.get(user_id)

    def end_conversation(self, conversation_id: str) -> Optional[str]:
        """
        结束对话并生成学习报告
        
        Returns:
            学习报告文本（如果report_service可用）
        """
        conversation = self.conversation_repo.get(conversation_id)
        if not conversation:
            return None
        
        conversation.state = ConversationState.COMPLETED
        
        # 生成学习报告
        report = None
        if self.report_service:
            try:
                user_profile = self.user_repo.get(conversation.user_id)
                if user_profile:
                    # 提取评估历史
                    assessment_history = []
                    for msg in conversation.messages:
                        if msg.metadata and "assessment" in msg.metadata:
                            assess_data = msg.metadata["assessment"]
                            if isinstance(assess_data, dict):
                                # 这里需要从dict重建AssessmentResult对象
                                # 简化处理：直接传递dict
                                from models.assessment import DimensionScore, AbilityProfile
                                from models.user import CEFRLevel
                                
                                dim_scores = [
                                    DimensionScore(**dim) 
                                    for dim in assess_data.get("dimension_scores", [])
                                ]
                                ability_profile = AbilityProfile(
                                    overall_score=assess_data.get("ability_profile", {}).get("overall_score", 0),
                                    cefr_level=CEFRLevel(assess_data.get("ability_profile", {}).get("cefr_level", "A1")),
                                    strengths=assess_data.get("ability_profile", {}).get("strengths", []),
                                    weaknesses=assess_data.get("ability_profile", {}).get("weaknesses", []),
                                    confidence=assess_data.get("ability_profile", {}).get("confidence", 0.5)
                                )
                                assessment_result = AssessmentResult(
                                    round_number=assess_data.get("round_number", 0),
                                    dimension_scores=dim_scores,
                                    ability_profile=ability_profile,
                                    raw_response=assess_data.get("raw_response", {}),
                                    timestamp=assess_data.get("timestamp", "")
                                )
                                assessment_history.append(assessment_result)
                    
                    report = self.report_service.generate_learning_report(
                        conversation=conversation,
                        user_profile=user_profile,
                        assessment_history=assessment_history
                    )
                    logger.info(f"[end_conversation] Learning report generated for conversation {conversation_id}")
            except Exception as e:
                logger.error(f"[end_conversation] Failed to generate report: {e}")
        
        # 保存对话
        self.conversation_repo.save(conversation)
        
        return report
