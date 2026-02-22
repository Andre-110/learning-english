"""
CEFR等级映射器 - 将分数映射到CEFR等级
"""
from models.user import CEFRLevel


class CEFRMapper:
    """CEFR等级映射器 - 根据分数确定CEFR等级"""
    
    # 分数到CEFR等级的映射范围
    # 注意：B1包含75分，B2从75.1分开始
    SCORE_RANGES = {
        CEFRLevel.A1: (0, 30),
        CEFRLevel.A2: (30, 50),
        CEFRLevel.B1: (50, 75.1),  # 调整：50-75分（包含75）对应B1
        CEFRLevel.B2: (75, 85),    # 调整：75.1-85分对应B2（75分属于B1）
        CEFRLevel.C1: (85, 95),
        CEFRLevel.C2: (95, 100),
    }
    
    @classmethod
    def score_to_cefr(cls, score: float) -> CEFRLevel:
        """
        根据分数映射到CEFR等级
        
        Args:
            score: 综合能力分数 (0-100)
            
        Returns:
            CEFR等级
        """
        # 确保分数在有效范围内
        score = max(0.0, min(100.0, score))
        
        # 从高到低检查等级范围
        # 特殊处理B1和B2的边界（75分属于B1）
        if 50 <= score <= 75:
            return CEFRLevel.B1
        
        for level in [CEFRLevel.C2, CEFRLevel.C1, CEFRLevel.B2, CEFRLevel.A2, CEFRLevel.A1]:
            min_score, max_score = cls.SCORE_RANGES[level]
            # C2的上限是100（包含）
            if level == CEFRLevel.C2:
                if min_score <= score <= max_score:
                    return level
            elif level == CEFRLevel.B2:
                # B2从75.1开始（不包含75）
                if 75 < score < max_score:
                    return level
            elif level == CEFRLevel.A1:
                # A1的下限包含0
                if min_score <= score < max_score:
                    return level
            else:
                # 其他等级：下限包含，上限不包含
                if min_score <= score < max_score:
                    return level
        
        # 默认返回A1
        return CEFRLevel.A1
    
    @classmethod
    def get_score_range(cls, level: CEFRLevel) -> tuple:
        """
        获取某个CEFR等级对应的分数范围
        
        Args:
            level: CEFR等级
            
        Returns:
            (最低分, 最高分) 元组
        """
        return cls.SCORE_RANGES.get(level, (0, 30))
    
    @classmethod
    def is_score_aligned_with_level(cls, score: float, level: CEFRLevel) -> bool:
        """
        检查分数是否与等级对齐
        
        Args:
            score: 综合能力分数
            level: CEFR等级
            
        Returns:
            是否对齐
        """
        expected_level = cls.score_to_cefr(score)
        return expected_level == level

