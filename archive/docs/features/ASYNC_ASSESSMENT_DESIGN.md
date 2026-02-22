# 异步评估设计方案

## 问题分析

### 当前同步流程的问题
```
用户回答 → 评估（同步，耗时）→ 更新画像 → 生成问题 → 发送
         ⏸️ 阻塞在这里（2-5秒）
```

### 异步化的挑战
如果改为异步：
```
用户回答 → 立即生成问题（使用旧画像）→ 发送
         → 评估（异步）→ 更新画像
```
**问题**：下一次对话使用的是旧的画像数据，无法动态调整。

---

## 解决方案：快速评估 + 完整评估

### 设计思路

采用**两阶段评估**策略：

1. **快速评估（同步，<500ms）**
   - 基于规则或简化的LLM调用
   - 快速估算能力画像
   - 用于立即生成下一个问题

2. **完整评估（异步，后台）**
   - 完整的LLM评估
   - 详细的强项/弱项分析
   - 更新用户画像

### 执行流程

```
用户回答
    ↓
快速评估（同步，<500ms）
    ├─ 估算分数和等级
    └─ 简单分析
    ↓
生成下一个问题（使用快速评估结果）
    ↓
发送问题和开始TTS
    ↓
完整评估（异步，后台）
    ├─ 详细评估
    ├─ 更新用户画像
    └─ 发送评估结果到前端
```

---

## 实现方案

### 方案1：快速评估（推荐）

**优点**：
- 响应快，用户体验好
- 下一个问题基于当前回答的快速评估
- 完整评估在后台进行，不影响响应速度

**实现**：
1. 创建 `QuickEvaluator` 服务
2. 快速评估基于：
   - 回答长度
   - 词汇复杂度（简单统计）
   - 语法错误（简单检测）
   - 历史评估趋势（预测）

### 方案2：使用历史数据 + 增量更新

**优点**：
- 不需要快速评估
- 基于历史数据预测

**实现**：
1. 使用上一次的评估结果
2. 基于当前回答的简单特征（长度、词汇）做增量调整
3. 完整评估在后台进行

### 方案3：延迟问题生成（不推荐）

**优点**：
- 保证准确性

**缺点**：
- 仍然需要等待评估
- 用户体验差

---

## 推荐实现：方案1（快速评估）

### 代码结构

```python
# services/quick_evaluator.py
class QuickEvaluator:
    def quick_evaluate(self, user_response: str, previous_assessment: dict) -> dict:
        """
        快速评估（<500ms）
        返回：{
            "overall_score": float,
            "cefr_level": str,
            "confidence": float  # 置信度
        }
        """
        # 1. 基于回答长度
        # 2. 基于词汇复杂度
        # 3. 基于历史趋势
        # 4. 简单规则判断
        pass

# core/conversation.py
def process_user_response_async(self, ...):
    # 1. 快速评估（同步）
    quick_assessment = self.quick_evaluator.quick_evaluate(...)
    
    # 2. 使用快速评估生成问题
    next_question = self.generator_service.generate_question(
        ability_profile=quick_assessment
    )
    
    # 3. 返回问题和快速评估
    return conversation, quick_assessment, next_question
    
    # 4. 后台进行完整评估（异步）
    asyncio.create_task(self._full_assessment_async(...))
```

### 异步完整评估

```python
async def _full_assessment_async(self, conversation_id, user_response):
    # 完整评估
    full_assessment = self.evaluator_service.evaluate(...)
    
    # 更新用户画像
    user_profile = self.user_repo.get(...)
    user_profile.update_from_assessment(full_assessment)
    self.user_repo.save(user_profile)
    
    # 发送评估结果到前端（如果WebSocket还连接）
    # 或者保存到数据库，下次对话时使用
```

---

## 数据一致性保证

### 问题：快速评估 vs 完整评估可能不一致

**解决方案**：
1. **下一次对话使用完整评估结果**
   - 完整评估完成后更新用户画像
   - 下一次对话时读取最新的画像

2. **前端显示两个评估**
   - 快速评估：立即显示（标记为"初步评估"）
   - 完整评估：完成后更新（标记为"最终评估"）

3. **如果差异大，可以调整**
   - 如果完整评估与快速评估差异很大
   - 可以在下一轮对话中发送一个补充问题

---

## 实现步骤

1. **创建快速评估服务**
   - `services/quick_evaluator.py`
   - 实现快速评估逻辑

2. **修改对话处理流程**
   - `core/conversation.py`
   - 添加快速评估调用
   - 添加异步完整评估

3. **修改WebSocket端点**
   - `api/streaming_voice_endpoint.py`
   - 使用快速评估结果立即生成问题
   - 后台执行完整评估

4. **前端处理**
   - 接收快速评估结果（立即显示）
   - 接收完整评估结果（更新显示）

---

## 性能对比

### 当前（同步）
- 总响应时间：3-8秒
- 用户体验：需要等待

### 异步（快速评估）
- 快速评估：<500ms
- 问题生成：1-2秒
- 总响应时间：1.5-2.5秒（提升60-70%）
- 完整评估：后台进行，不影响响应

---

## 风险评估

1. **快速评估准确性**
   - 风险：快速评估可能不够准确
   - 缓解：使用历史数据+简单规则，置信度标记

2. **数据一致性**
   - 风险：快速评估和完整评估可能不一致
   - 缓解：下一次对话使用完整评估结果

3. **复杂度增加**
   - 风险：代码复杂度增加
   - 缓解：清晰的代码结构和文档

