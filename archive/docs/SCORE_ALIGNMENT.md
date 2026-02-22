# 分数与CEFR等级对齐说明

## 实现说明

已实现分数与CEFR等级的自动对齐功能，确保相同分数对应相同的CEFR等级。

## 映射规则

| CEFR等级 | 分数范围 | 说明 |
|---------|---------|------|
| A1 | 0-30分 | 初学者 |
| A2 | 30-50分 | 基础水平 |
| B1 | 50-75分 | 中级水平（**包含75分**） |
| B2 | 75-85分 | 中高级水平（从75.1分开始） |
| C1 | 85-95分 | 高级水平 |
| C2 | 95-100分 | 精通水平 |

### 边界说明

- **75分属于B1**：确保75分统一映射到B1等级
- **75.1分开始属于B2**：从75.1分开始映射到B2等级

## 实现方式

### 1. CEFR映射器 (`core/cefr_mapper.py`)

创建了`CEFRMapper`类，提供以下功能：

- `score_to_cefr(score)`: 根据分数映射到CEFR等级
- `get_score_range(level)`: 获取某个等级对应的分数范围
- `is_score_aligned_with_level(score, level)`: 检查分数是否与等级对齐

### 2. 评估服务集成 (`services/evaluator.py`)

在评估服务中集成了CEFR映射器：

```python
# 根据分数映射CEFR等级（确保分数与等级对齐）
overall_score = float(profile_data.get("overall_score", 50.0))
mapped_cefr_level = CEFRMapper.score_to_cefr(overall_score)

# 如果LLM返回的等级与分数不对齐，使用映射后的等级
if not CEFRMapper.is_score_aligned_with_level(overall_score, CEFRLevel(llm_cefr_level)):
    logger.info(f"CEFR level adjusted: LLM={llm_cefr_level} -> Mapped={mapped_cefr_level.value}")
```

## 效果

### 之前的问题
- 相同分数（75分）可能对应不同等级（A2或B1）
- LLM独立判断等级，不完全依赖分数

### 现在的效果
- ✅ 相同分数统一对应相同等级
- ✅ 75分统一映射到B1等级
- ✅ 分数与等级完全对齐

## 测试

运行测试脚本验证映射功能：

```bash
python test/test_cefr_mapper.py
```

测试包括：
1. 分数到CEFR等级映射测试
2. 分数范围测试
3. 分数与等级对齐测试

## 使用示例

```python
from core.mapper import CEFRMapper
from models.user import CEFRLevel

# 根据分数获取CEFR等级
level = CEFRMapper.score_to_cefr(75.0)  # 返回 B1
level = CEFRMapper.score_to_cefr(85.0)  # 返回 C1

# 检查分数是否与等级对齐
is_aligned = CEFRMapper.is_score_aligned_with_level(75.0, CEFRLevel.B1)  # True
is_aligned = CEFRMapper.is_score_aligned_with_level(75.0, CEFRLevel.A2)  # False

# 获取等级对应的分数范围
min_score, max_score = CEFRMapper.get_score_range(CEFRLevel.B1)  # (50, 75.1)
```

## 注意事项

1. **LLM评估仍然有效**：LLM仍然会评估维度评分和能力特征
2. **等级自动对齐**：最终CEFR等级会根据分数自动映射，确保一致性
3. **日志记录**：如果LLM返回的等级与分数不对齐，会在日志中记录调整信息

## 映射表

| 分数 | CEFR等级 |
|------|---------|
| 0-29.9 | A1 |
| 30-49.9 | A2 |
| 50-75.0 | B1 |
| 75.1-84.9 | B2 |
| 85-94.9 | C1 |
| 95-100 | C2 |

## 总结

通过实现CEFR映射器，确保了：
- ✅ 分数与等级的一致性
- ✅ 相同分数对应相同等级
- ✅ 评估结果的可预测性





