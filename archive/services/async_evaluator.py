"""
异步评估服务 - 使用独立的agent在后台执行评估
"""
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from models.assessment import AssessmentResult, DimensionScore, AbilityProfile
from models.user import CEFRLevel
from models.conversation import Message, MessageRole
from services.evaluator import EvaluatorService
from services.utils.logger import get_logger

logger = get_logger("services.async_evaluator")


class AsyncEvaluatorService:
    """异步评估服务 - 在后台执行完整评估"""
    
    def __init__(self, evaluator_service: EvaluatorService):
        """
        初始化异步评估服务
        
        Args:
            evaluator_service: 同步评估服务实例
        """
        self.evaluator_service = evaluator_service
        self._running_tasks = {}  # 跟踪正在运行的评估任务
    
    async def evaluate_async(
        self,
        conversation_id: str,
        conversation_messages: List[Message],
        user_response: str,
        round_number: int,
        previous_assessments: Optional[List[Dict[str, Any]]] = None,
        callback: Optional[callable] = None
    ) -> None:
        """
        异步执行评估（不阻塞）
        
        Args:
            conversation_id: 对话ID
            conversation_messages: 对话消息列表
            user_response: 用户回答
            round_number: 当前轮次
            previous_assessments: 历史评估记录
            callback: 评估完成后的回调函数 callback(conversation_id, assessment_result)
        """
        logger.info(f"[evaluate_async] 启动异步评估任务: conversation_id={conversation_id}, round={round_number}")
        
        # 创建异步任务
        task = asyncio.create_task(
            self._evaluate_task(
                conversation_id=conversation_id,
                conversation_messages=conversation_messages,
                user_response=user_response,
                round_number=round_number,
                previous_assessments=previous_assessments,
                callback=callback
            )
        )
        
        # 记录任务
        task_key = f"{conversation_id}_{round_number}"
        self._running_tasks[task_key] = task
        
        # 任务完成后清理
        task.add_done_callback(lambda t: self._running_tasks.pop(task_key, None))
        
        logger.info(f"[evaluate_async] 异步评估任务已创建: {task_key}")
    
    async def _evaluate_task(
        self,
        conversation_id: str,
        conversation_messages: List[Message],
        user_response: str,
        round_number: int,
        previous_assessments: Optional[List[Dict[str, Any]]] = None,
        callback: Optional[callable] = None
    ) -> AssessmentResult:
        """
        执行评估任务（在后台运行）
        
        Args:
            conversation_id: 对话ID
            conversation_messages: 对话消息列表
            user_response: 用户回答
            round_number: 当前轮次
            previous_assessments: 历史评估记录
            callback: 评估完成后的回调函数
            
        Returns:
            评估结果
        """
        try:
            logger.info(f"[_evaluate_task] 开始执行评估: conversation_id={conversation_id}, round={round_number}")
            
            # 在线程池中执行同步评估（避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            assessment_result = await loop.run_in_executor(
                None,  # 使用默认线程池
                self._run_evaluation,
                conversation_messages,
                user_response,
                round_number,
                previous_assessments
            )
            
            logger.info(
                f"[_evaluate_task] 评估完成: conversation_id={conversation_id}, "
                f"score={assessment_result.ability_profile.overall_score}, "
                f"level={assessment_result.ability_profile.cefr_level.value}"
            )
            
            # 执行回调
            if callback:
                try:
                    await callback(conversation_id, assessment_result)
                except Exception as e:
                    logger.error(f"[_evaluate_task] 回调执行失败: {e}", exc_info=True)
            
            return assessment_result
            
        except Exception as e:
            logger.error(f"[_evaluate_task] 评估任务失败: {e}", exc_info=True)
            raise
    
    def _run_evaluation(
        self,
        conversation_messages: List[Message],
        user_response: str,
        round_number: int,
        previous_assessments: Optional[List[Dict[str, Any]]] = None
    ) -> AssessmentResult:
        """
        在线程池中运行同步评估
        
        Args:
            conversation_messages: 对话消息列表
            user_response: 用户回答
            round_number: 当前轮次
            previous_assessments: 历史评估记录
            
        Returns:
            评估结果
        """
        return self.evaluator_service.evaluate(
            conversation_messages=conversation_messages,
            current_response=user_response,
            round_number=round_number,
            previous_assessments=previous_assessments
        )
    
    def get_running_tasks_count(self) -> int:
        """获取正在运行的评估任务数量"""
        return len(self._running_tasks)
    
    async def wait_for_task(self, conversation_id: str, round_number: int, timeout: Optional[float] = None) -> Optional[AssessmentResult]:
        """
        等待指定任务完成
        
        Args:
            conversation_id: 对话ID
            round_number: 轮次
            timeout: 超时时间（秒）
            
        Returns:
            评估结果，如果超时则返回None
        """
        task_key = f"{conversation_id}_{round_number}"
        task = self._running_tasks.get(task_key)
        
        if not task:
            logger.warning(f"[wait_for_task] 任务不存在: {task_key}")
            return None
        
        try:
            if timeout:
                result = await asyncio.wait_for(task, timeout=timeout)
            else:
                result = await task
            return result
        except asyncio.TimeoutError:
            logger.warning(f"[wait_for_task] 任务超时: {task_key}")
            return None
        except Exception as e:
            logger.error(f"[wait_for_task] 等待任务失败: {e}", exc_info=True)
            return None





