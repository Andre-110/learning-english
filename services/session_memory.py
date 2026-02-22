"""
会话内存管理器 - 即时消费兴趣点、优点、缺点

设计目标：
1. 兴趣点 (Interests) - 即时消费
   - 每轮对话后立即更新到内存
   - 下一轮 Prompt 立即使用新兴趣
   - 会话结束时批量持久化到 DB
   - 权重计算: (历史频次 × 0.7) + (本轮出现 × 0.3)

2. 优点 (Strengths) - 即时正向反馈
   - 检测到高级词汇/复杂句式时记录
   - 下一轮 Prompt 提示 AI 给予表扬
   - 按独特性保留 Top 5

3. 缺点 (Weaknesses) - 策略性训练
   - 累计错误计数
   - 达到阈值（3次）后才触发 Prompt 提示
   - 按频次保留 Top 5
"""
from typing import Dict, Any, List, Optional
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionMemory:
    """
    会话内存 - 管理单次会话的即时数据
    
    用于在会话期间跟踪用户的兴趣点、优点和缺点，
    实现"即时消费"的动态 Prompt 注入。
    """
    
    # 即时兴趣点（本轮提取，立即可用于下一轮）
    interests: List[str] = field(default_factory=list)
    interest_counts: Dict[str, int] = field(default_factory=dict)  # 兴趣出现次数
    
    # 即时优点（检测到时记录，用于正向反馈）
    strengths: List[str] = field(default_factory=list)
    recent_strength: Optional[str] = None  # 最近一轮检测到的优点（用于即时表扬）
    
    # 缺点计数（累计错误，达到阈值才触发）
    weakness_counts: Counter = field(default_factory=Counter)
    triggered_weaknesses: List[str] = field(default_factory=list)  # 已触发的缺点（需要纠正）
    
    # 配置
    WEAKNESS_THRESHOLD: int = 3  # 错误出现3次后触发纠正提示
    
    def update_interests(self, new_interests: List[str]):
        """
        更新兴趣点 - 即时消费
        
        每轮对话后调用，新兴趣立即可用于下一轮 Prompt
        """
        for interest in new_interests:
            if interest and isinstance(interest, str):
                interest = interest.strip().lower()
                if interest:
                    self.interest_counts[interest] = self.interest_counts.get(interest, 0) + 1
                    if interest not in self.interests:
                        self.interests.append(interest)
    
    def get_current_interests(self) -> List[str]:
        """
        获取当前会话的兴趣点（按出现频次排序，Top 10）
        
        用于注入到交互轨 Prompt
        """
        sorted_interests = sorted(
            self.interest_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [interest for interest, _ in sorted_interests[:10]]
    
    def update_strengths(self, new_strengths: List[str]):
        """
        更新优点 - 即时正向反馈
        
        检测到高级词汇或复杂句式时调用
        """
        for strength in new_strengths:
            if strength and isinstance(strength, str):
                strength = strength.strip()
                if strength and strength not in self.strengths:
                    self.strengths.append(strength)
                    self.recent_strength = strength  # 记录最近的优点，用于即时表扬
        
        # 保留最独特的 5 个（按添加顺序，最新的优先）
        if len(self.strengths) > 5:
            self.strengths = self.strengths[-5:]
    
    def get_recent_strength_for_praise(self) -> Optional[str]:
        """
        获取最近的优点（用于下一轮 AI 给予表扬）
        
        获取后清空，避免重复表扬
        """
        strength = self.recent_strength
        self.recent_strength = None  # 清空，只表扬一次
        return strength
    
    def update_weaknesses(self, new_weaknesses: List[str]):
        """
        更新缺点 - 策略性训练
        
        累计错误计数，达到阈值后才触发纠正提示
        """
        for weakness in new_weaknesses:
            if weakness and isinstance(weakness, str):
                weakness = weakness.strip().lower()
                if weakness:
                    self.weakness_counts[weakness] += 1
                    
                    # 检查是否达到阈值
                    if (self.weakness_counts[weakness] >= self.WEAKNESS_THRESHOLD and 
                        weakness not in self.triggered_weaknesses):
                        self.triggered_weaknesses.append(weakness)
    
    def get_triggered_weaknesses(self) -> List[str]:
        """
        获取已触发的缺点（需要在 Prompt 中引导纠正）
        
        只返回达到阈值的缺点
        """
        return self.triggered_weaknesses.copy()
    
    def get_weakness_for_correction(self) -> Optional[str]:
        """
        获取一个需要纠正的缺点（用于下一轮 AI 引导练习）
        
        优先返回频次最高的缺点
        """
        if not self.triggered_weaknesses:
            return None
        
        # 按频次排序，返回最频繁的
        triggered_with_counts = [
            (w, self.weakness_counts[w]) 
            for w in self.triggered_weaknesses
        ]
        triggered_with_counts.sort(key=lambda x: x[1], reverse=True)
        return triggered_with_counts[0][0] if triggered_with_counts else None
    
    def merge_with_db_interests(
        self, 
        db_interests: List[str],
        history_weight: float = 0.7,
        session_weight: float = 0.3
    ) -> List[str]:
        """
        合并会话兴趣点与数据库历史兴趣点
        
        权重计算: (历史频次 × 0.7) + (本轮出现 × 0.3)
        
        Args:
            db_interests: 数据库中的历史兴趣点
            history_weight: 历史权重
            session_weight: 本轮权重
            
        Returns:
            合并后的 Top 10 兴趣点
        """
        # 计算综合权重
        combined_weights: Dict[str, float] = {}
        
        # 历史兴趣（按顺序给权重，越靠前权重越高）
        for i, interest in enumerate(db_interests):
            interest = interest.strip().lower() if isinstance(interest, str) else ""
            if interest:
                # 历史权重：越靠前的越重要
                position_weight = 1.0 - (i * 0.1)  # 第1个=1.0, 第10个=0.1
                combined_weights[interest] = position_weight * history_weight
        
        # 本轮兴趣（按出现次数加权）
        max_count = max(self.interest_counts.values()) if self.interest_counts else 1
        for interest, count in self.interest_counts.items():
            frequency_weight = count / max_count  # 归一化
            if interest in combined_weights:
                combined_weights[interest] += frequency_weight * session_weight
            else:
                combined_weights[interest] = frequency_weight * session_weight
        
        # 按权重排序，返回 Top 10
        sorted_interests = sorted(
            combined_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [interest for interest, _ in sorted_interests[:10]]
    
    def merge_with_db_strengths(self, db_strengths: List[str]) -> List[str]:
        """
        合并会话优点与数据库历史优点
        
        按独特性保留 Top 5（优先保留高级词汇/复杂句式）
        
        Args:
            db_strengths: 数据库中的历史优点
            
        Returns:
            合并后的 Top 5 优点
        """
        # 合并去重
        all_strengths = list(db_strengths) if db_strengths else []
        for s in self.strengths:
            if s not in all_strengths:
                all_strengths.append(s)
        
        # 保留最近的 5 个（新的优先）
        return all_strengths[-5:] if len(all_strengths) > 5 else all_strengths
    
    def merge_with_db_weaknesses(self, db_weaknesses: List[str]) -> List[str]:
        """
        合并会话缺点与数据库历史缺点
        
        按频次保留 Top 5（重复犯的错误优先）
        
        Args:
            db_weaknesses: 数据库中的历史缺点
            
        Returns:
            合并后的 Top 5 缺点
        """
        # 合并计数
        combined_counts: Counter = Counter()
        
        # 历史缺点（假设都出现过至少1次）
        for w in (db_weaknesses or []):
            if isinstance(w, str) and w.strip():
                combined_counts[w.strip().lower()] += 1
        
        # 本轮缺点
        for w, count in self.weakness_counts.items():
            combined_counts[w] += count
        
        # 按频次排序，返回 Top 5
        most_common = combined_counts.most_common(5)
        return [w for w, _ in most_common]
    
    def get_prompt_context(self) -> Dict[str, Any]:
        """
        获取用于 Prompt 注入的上下文数据
        
        Returns:
            {
                "session_interests": [...],  # 本轮新兴趣
                "praise_strength": "...",    # 需要表扬的优点（或 None）
                "correct_weakness": "..."    # 需要纠正的缺点（或 None）
            }
        """
        return {
            "session_interests": self.get_current_interests(),
            "praise_strength": self.get_recent_strength_for_praise(),
            "correct_weakness": self.get_weakness_for_correction()
        }
    
    def get_context_for_interaction(self) -> Dict[str, Any]:
        """
        [DEPRECATED] 获取用于交互轨 Prompt 的上下文数据
        
        ⚠️ 此方法已废弃。由于评估轨异步执行，即时数据存在时序错乱风险。
        交互轨现在统一从 user_profile 读取持久化数据，不再使用 session_context。
        
        保留此方法仅供参考，未来版本可能移除。
        
        Returns:
            {
                "new_strengths": [...],         # 本轮新发现的优点（需要表扬）
                "triggered_weaknesses": [...],  # 已触发的缺点（需要策略性训练）
                "recent_interests": [...]       # 最近的兴趣点（用于话题引导）
            }
        """
        return {
            "new_strengths": [self.recent_strength] if self.recent_strength else [],
            "triggered_weaknesses": self.get_triggered_weaknesses(),
            "recent_interests": self.get_current_interests()[:3]  # 最近3个兴趣
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "interests": self.interests,
            "interest_counts": dict(self.interest_counts),
            "strengths": self.strengths,
            "weakness_counts": dict(self.weakness_counts),
            "triggered_weaknesses": self.triggered_weaknesses
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMemory":
        """从字典反序列化"""
        memory = cls()
        memory.interests = data.get("interests", [])
        memory.interest_counts = data.get("interest_counts", {})
        memory.strengths = data.get("strengths", [])
        memory.weakness_counts = Counter(data.get("weakness_counts", {}))
        memory.triggered_weaknesses = data.get("triggered_weaknesses", [])
        return memory
    
    @classmethod
    def from_user_profile(cls, user_profile: Optional[Dict[str, Any]] = None) -> "SessionMemory":
        """
        从用户画像创建会话内存
        
        初始化时不加载历史数据到 session，只在合并时使用
        
        Args:
            user_profile: 用户画像（从数据库加载）
            
        Returns:
            空的 SessionMemory 实例
        """
        # 创建空的会话内存
        # 历史数据在合并时通过参数传入，不预加载
        return cls()
