"""
热点内容池管理模块

用于在对话过程中积累和选择热点内容
"""

from typing import Dict, Any, List, Optional
import logging

# 兼容不同的导入路径
try:
    from utils.logger import get_logger
    logger = get_logger("services.hot_content_pool")
except ImportError:
    logger = logging.getLogger("services.hot_content_pool")

# 池大小限制
MAX_POOL_SIZE = 10


def create_hot_content_context() -> Dict[str, Any]:
    """创建热点内容上下文（每个 WebSocket 会话一个）"""
    return {
        "pool": [],                # 热点池: [{"topic", "headline", "detail", "search_turn", "used"}]
        "searched_topics": set(),  # 已搜索话题（避免重复搜索）
        "turn_count": 0,           # 当前轮次
        "last_inject_turn": -10,   # 上次注入的轮次
        "inject_count": 0,         # 已注入次数
        "min_interval": 3,         # 两次注入最小间隔轮次
        "max_inject": 5,           # 最多注入次数
    }


def add_to_pool(
    hot_content_context: Dict[str, Any],
    topic: str,
    headline: str,
    detail: str,
    search_turn: int
) -> bool:
    """
    将热点内容加入池中
    
    Returns:
        是否成功加入（池满时可能淘汰旧的）
    """
    pool = hot_content_context.get("pool", [])
    
    # 检查是否已存在相同话题
    for hot in pool:
        if hot.get("topic") == topic:
            logger.info(f"[热点池] 话题已存在，跳过: {topic}")
            return False
    
    # 池满时淘汰最早的未使用热点
    if len(pool) >= MAX_POOL_SIZE:
        removed = False
        for i, hot in enumerate(pool):
            if not hot.get("used"):
                removed_topic = pool.pop(i).get("topic")
                logger.info(f"[热点池] 池满，淘汰旧热点: {removed_topic}")
                removed = True
                break
        if not removed:
            # 所有都已使用，淘汰最早的
            removed_topic = pool.pop(0).get("topic")
            logger.info(f"[热点池] 池满，淘汰已使用热点: {removed_topic}")
    
    # 加入新热点
    pool.append({
        "topic": topic,
        "headline": headline,
        "detail": detail,
        "search_turn": search_turn,
        "used": False
    })
    hot_content_context["pool"] = pool
    logger.info(f"[热点池] ✅ 热点入池: {topic} | 标题: {headline[:40]}... | 池中共 {len(pool)} 个")
    return True


def _is_user_asking_question(conversation_history: List[Dict[str, Any]]) -> bool:
    """
    检测用户最后一条消息是否在提问
    
    如果用户在提问，应该优先回答用户，跳过热点注入
    """
    if not conversation_history:
        return False
    
    # 获取最后一条用户消息
    last_user_msg = None
    for msg in reversed(conversation_history):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break
    
    if not last_user_msg:
        return False
    
    # 检测问号
    if "?" in last_user_msg:
        return True
    
    # 检测常见提问模式
    question_patterns = [
        "do you have", "can you", "could you", "would you",
        "how do", "how can", "how to", "what is", "what are",
        "tell me", "show me", "give me", "help me",
        "any suggestions", "any tips", "any advice",
        "recommend", "recipe", "example"
    ]
    lower_msg = last_user_msg.lower()
    for pattern in question_patterns:
        if pattern in lower_msg:
            return True
    
    return False


def select_best_hot_content(
    hot_content_context: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    current_turn: int
) -> Optional[Dict[str, Any]]:
    """
    从热点池中选择最佳热点
    
    选择策略：
    1. 用户提问检测：如果用户在提问，跳过注入，优先回答
    2. 频率控制：距上次注入至少间隔 min_interval 轮
    3. 最大次数：不超过 max_inject 次
    4. 相关性：热点话题的关键词在近期对话中出现
    5. 选择最早未使用的热点（FIFO）
    
    Returns:
        选中的热点内容，或 None
    """
    pool = hot_content_context.get("pool", [])
    last_inject_turn = hot_content_context.get("last_inject_turn", -10)
    min_interval = hot_content_context.get("min_interval", 3)
    max_inject = hot_content_context.get("max_inject", 5)
    inject_count = hot_content_context.get("inject_count", 0)
    
    # 🆕 检查用户是否在提问 - 如果是，优先回答用户，跳过热点注入
    if _is_user_asking_question(conversation_history):
        logger.info(f"[热点池] ⏸️ 用户在提问，跳过热点注入，优先回答")
        return None
    
    # 检查是否达到最大注入次数
    if inject_count >= max_inject:
        logger.debug(f"[热点池] 已达最大注入次数 {max_inject}")
        return None
    
    # 检查频率限制
    if (current_turn - last_inject_turn) < min_interval:
        logger.debug(f"[热点池] 频率限制: 距上次注入 {current_turn - last_inject_turn} 轮 < {min_interval}")
        return None
    
    # 获取近期对话文本（用于相关性检查）
    recent_text = " ".join([
        m.get("content", "") for m in conversation_history[-4:]
    ]).lower()
    
    # 遍历热点池，选择最早的未使用且相关的热点
    for hot in pool:
        if hot.get("used"):
            continue
        
        # 检查相关性：热点话题关键词是否在近期对话中
        topic = hot.get("topic", "").lower()
        topic_words = [w for w in topic.split() if len(w) > 3]
        
        is_relevant = True  # 默认相关
        if topic_words:
            # 如果有关键词，检查是否至少一个在对话中
            is_relevant = any(word in recent_text for word in topic_words)
        
        if is_relevant:
            logger.info(f"[热点池] 选中相关热点: {hot.get('topic')}")
            return hot
    
    # 如果没有相关的，选择最早的未使用热点
    for hot in pool:
        if not hot.get("used"):
            logger.info(f"[热点池] 无相关热点，选择最早未使用: {hot.get('topic')}")
            return hot
    
    logger.debug("[热点池] 无可用热点")
    return None


def mark_used(
    hot_content_context: Dict[str, Any],
    hot_content: Dict[str, Any],
    current_turn: int
):
    """标记热点已使用"""
    hot_content["used"] = True
    hot_content_context["last_inject_turn"] = current_turn
    hot_content_context["inject_count"] = hot_content_context.get("inject_count", 0) + 1
    logger.info(f"[热点池] 🔥 热点注入: {hot_content.get('topic')} | Turn {current_turn} | 第 {hot_content_context['inject_count']} 次")


def get_pool_stats(hot_content_context: Dict[str, Any]) -> Dict[str, Any]:
    """获取热点池统计信息"""
    pool = hot_content_context.get("pool", [])
    return {
        "total": len(pool),
        "unused": sum(1 for h in pool if not h.get("used")),
        "used": sum(1 for h in pool if h.get("used")),
        "searched_topics": list(hot_content_context.get("searched_topics", set())),
        "inject_count": hot_content_context.get("inject_count", 0),
        "last_inject_turn": hot_content_context.get("last_inject_turn", -10),
    }
