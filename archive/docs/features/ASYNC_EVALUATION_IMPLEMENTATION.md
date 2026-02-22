# 异步评估实现文档

## 概述

已实现异步评估服务，使用独立的agent在后台执行完整评估，大幅提升响应速度。

## 架构设计

### 执行流程

```
用户回答
    ↓
快速评估（同步，<500ms）
    ├─ 基于规则和简单分析
    ├─ 估算分数和等级
    └─ 使用历史数据预测
    ↓
生成下一个问题（使用快速评估结果）✅
    ↓
立即发送问题和开始TTS ✅
    ↓
完整评估（异步，后台，2-5秒）
    ├─ 使用独立的LLM agent
    ├─ 详细评估和分析
    ├─ 更新用户画像到数据库 ✅
    └─ 发送完整评估结果到前端
```

## 核心组件

### 1. QuickEvaluatorService（快速评估服务）

**文件**: `services/quick_evaluator.py`

**功能**:
- 基于规则和简单分析的快速评估（<500ms）
- 评估维度：
  - 回答长度
  - 词汇复杂度
  - 语法结构
  - 历史趋势

**返回结果**:
```python
{
    "overall_score": float,      # 综合分数
    "cefr_level": str,           # CEFR等级
    "strengths": List[str],      # 强项
    "weaknesses": List[str],     # 弱项
    "confidence": float          # 置信度（0-1）
}
```

### 2. AsyncEvaluatorService（异步评估服务）

**文件**: `services/async_evaluator.py`

**功能**:
- 在后台执行完整评估（不阻塞主流程）
- 使用线程池执行同步评估（避免阻塞事件循环）
- 支持回调函数（评估完成后执行）

**关键方法**:
- `evaluate_async()`: 启动异步评估任务
- `_evaluate_task()`: 执行评估任务（在线程池中）
- `wait_for_task()`: 等待指定任务完成

### 3. ConversationManager（对话管理器）

**新增方法**: `process_user_response_quick()`

**功能**:
- 使用快速评估立即生成问题
- 不等待完整评估完成
- 返回快速评估结果和下一个问题

### 4. WebSocket端点

**文件**: `api/streaming_voice_endpoint.py`

**修改**:
- 使用 `process_user_response_quick()` 快速处理
- 立即发送快速评估结果和问题
- 启动异步评估任务（后台执行）
- 异步评估完成后更新用户画像并发送结果

### 5. 前端处理

**文件**: `static/app.js`

**修改**:
- 处理 `assessment` 消息（快速评估）
- 处理 `assessment_full` 消息（完整评估）
- 显示评估类型标记（快速/完整）
- 显示置信度

## 数据流

### 快速评估流程

```
用户回答
    ↓
process_user_response_quick()
    ├─ 快速评估（QuickEvaluatorService）
    ├─ 生成问题（使用快速评估结果）
    └─ 返回快速评估和问题
    ↓
发送到前端（立即）
    ├─ assessment 消息（快速评估）
    └─ question 消息（问题文本）
```

### 异步评估流程

```
启动异步任务
    ↓
AsyncEvaluatorService.evaluate_async()
    ├─ 创建异步任务
    └─ 在线程池中执行评估
    ↓
评估完成
    ↓
回调函数执行
    ├─ 更新用户画像
    ├─ 保存完整评估结果
    └─ 发送 assessment_full 消息到前端
```

## 性能对比

### 同步模式（之前）
- 总响应时间：3-8秒
- 用户体验：需要等待评估完成

### 异步模式（现在）
- 快速评估：<500ms
- 问题生成：1-2秒
- **总响应时间：1.5-2.5秒**（提升60-70%）
- 完整评估：后台进行，不影响响应

## 数据一致性

### 保证机制

1. **下一次对话使用完整评估结果**
   - 完整评估完成后更新用户画像到数据库
   - 下一次对话时从数据库读取最新的画像

2. **前端显示两个评估**
   - 快速评估：立即显示（标记为"快速"）
   - 完整评估：完成后更新（标记为"完整"）

3. **评估结果保存**
   - 快速评估：保存在消息元数据中（标记 `is_quick: true`）
   - 完整评估：保存在消息元数据中（`full_assessment`）

## 使用示例

### 后端代码

```python
# 快速处理（立即返回）
conversation, quick_assessment, next_question = manager.process_user_response_quick(
    conversation_id=conversation_id,
    user_response=normalized_text
)

# 启动异步评估（后台执行）
await manager.async_evaluator.evaluate_async(
    conversation_id=conversation_id,
    conversation_messages=context_messages,
    user_response=normalized_text,
    round_number=round_number,
    callback=assessment_callback  # 评估完成后的回调
)
```

### 前端代码

```javascript
// 处理快速评估
case 'assessment':
    updateAssessment(data.data, true);  // isQuick = true
    break;

// 处理完整评估
case 'assessment_full':
    updateAssessment(data.data, false);  // isQuick = false
    break;
```

## 配置

### 启用异步评估

异步评估服务在 `api/main.py` 中自动创建和注入：

```python
quick_evaluator = QuickEvaluatorService()
async_evaluator = AsyncEvaluatorService(evaluator_service)

manager = ConversationManager(
    ...,
    quick_evaluator=quick_evaluator,
    async_evaluator=async_evaluator
)
```

## 监控和调试

### 日志

- `[quick_evaluate]`: 快速评估日志
- `[evaluate_async]`: 异步评估启动日志
- `[_evaluate_task]`: 异步评估执行日志
- `[assessment_callback]`: 评估完成回调日志

### 任务跟踪

```python
# 获取正在运行的评估任务数量
count = async_evaluator.get_running_tasks_count()

# 等待指定任务完成
result = await async_evaluator.wait_for_task(conversation_id, round_number, timeout=10)
```

## 注意事项

1. **快速评估准确性**
   - 快速评估基于规则，可能不如完整评估准确
   - 置信度字段表示评估的可靠性

2. **WebSocket连接**
   - 如果WebSocket已断开，完整评估结果无法发送到前端
   - 但用户画像仍会更新到数据库

3. **资源使用**
   - 异步评估在后台运行，不会阻塞主流程
   - 但会增加系统资源使用（线程池）

## 未来优化

1. **快速评估改进**
   - 使用更复杂的规则
   - 基于历史数据的机器学习预测

2. **评估结果合并**
   - 如果快速评估和完整评估差异大，可以发送调整建议

3. **批量评估**
   - 支持批量评估多个回答

