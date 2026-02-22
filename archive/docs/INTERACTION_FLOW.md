# 每轮交互流程详解

## 一、完整交互流程概览

```
用户输入
    ↓
[1] 接收并存储用户回答
    ↓
[2] 准备上下文（对话历史 + 摘要）
    ↓
[3] 评估用户回答（LLM评估）
    ↓
[4] 更新用户画像
    ↓
[5] 自适应调整难度
    ↓
[6] 选择适配主题
    ↓
[7] 生成下一题（LLM生成）
    ↓
[8] 存储并返回
```

## 二、详细流程解析

### 阶段1：接收用户回答

**代码位置：** `core/conversation.py` - `process_user_response()`

```python
# 1. 获取对话对象
conversation = self.conversation_repo.get(conversation_id)

# 2. 添加用户消息到对话历史
conversation.add_message(MessageRole.USER, user_response)
```

**存储内容：**
- 消息角色：USER
- 消息内容：用户回答文本
- 时间戳：当前时间
- 元数据：空（后续会添加评估结果）

### 阶段2：准备上下文

**代码位置：** `services/context.py` - `get_context_messages()`

```python
# 获取用于LLM的上下文消息
context_messages = self.context_service.get_context_messages(
    conversation.messages,      # 完整消息列表
    conversation.summary,       # 对话摘要（如果有）
    conversation.summary_round # 摘要对应的轮数
)
```

**上下文组成：**
1. **系统消息**（如果有摘要）：
   ```
   [对话摘要（前5轮）]: 用户正在学习英语对话，整体水平B1...
   ```
2. **摘要后的消息**：从摘要轮数之后的所有消息

**目的：**
- 保持对话连贯性
- 控制上下文长度（通过摘要压缩）
- 减少token消耗

### 阶段3：评估用户回答

**代码位置：** `services/evaluator.py` - `evaluate()`

#### 3.1 构建评估提示词

**代码位置：** `prompts/builders.py` - `build_evaluation_prompt()`

```python
messages = [
    {
        "role": "system",
        "content": "你是一个名为'LinguaCoach'的智能英语对话测评系统..."
    },
    {
        "role": "user",
        "content": """
        [对话历史]
        user: I am a student.
        assistant: Can you tell me about your hobbies?
        user: I like reading books. 我喜欢读书。
        
        [当前用户回答]
        I read books every day.
        
        [评估任务]
        请从以下维度评分：
        1. 内容相关性
        2. 语言准确性
        3. 表达流利度
        4. 交互深度
        
        然后更新能力画像...
        """
    }
]
```

#### 3.2 LLM评估

**代码位置：** `services/llm.py` - `chat_completion_json()`

```python
# 调用LLM进行评估
response_json = self.llm_service.chat_completion_json(
    messages=messages,
    temperature=0.3  # 低温度保证一致性
)
```

**LLM返回的JSON格式：**
```json
{
    "dimension_scores": [
        {
            "dimension": "内容相关性",
            "score": 4.0,
            "comment": "直接回答了问题",
            "reasoning": "..."
        },
        {
            "dimension": "语言准确性",
            "score": 3.5,
            "comment": "语法基本正确",
            "reasoning": "..."
        },
        {
            "dimension": "表达流利度",
            "score": 4.0,
            "comment": "句子通顺",
            "reasoning": "..."
        },
        {
            "dimension": "交互深度",
            "score": 3.0,
            "comment": "回答较为简单",
            "reasoning": "..."
        }
    ],
    "ability_profile": {
        "overall_score": 72.5,
        "cefr_level": "B1",
        "strengths": ["基本表达流畅"],
        "weaknesses": ["语法准确性"],
        "confidence": 0.85
    }
}
```

#### 3.3 解析评估结果

**代码位置：** `services/evaluator.py` - `_parse_assessment_result()`

```python
# 解析JSON，创建AssessmentResult对象
assessment_result = AssessmentResult(
    round_number=round_number,
    dimension_scores=[...],      # 4个维度评分
    ability_profile=AbilityProfile(...),  # 能力画像
    raw_response=response_json,
    timestamp=datetime.now().isoformat()
)
```

### 阶段4：更新用户画像

**代码位置：** `models/user.py` - `update_from_assessment()`

```python
# 更新用户画像
user_profile.update_from_assessment(assessment_result)

# 更新内容：
# - overall_score: 72.5
# - cefr_level: B1
# - strengths: ["基本表达流畅"]
# - weaknesses: ["语法准确性"]
# - conversation_count: +1
# - last_updated: 当前时间
```

### 阶段5：自适应调整难度

**代码位置：** `core/adaptation.py` - `calculate_difficulty_adjustment()`

```python
# 根据用户表现调整难度
if current_score >= 80:
    # 表现优秀，提升难度
    suggested_level = get_next_level(current_level)  # B1 → B2
    adjustment = "increase"
elif current_score < 60:
    # 表现不佳，降低难度
    suggested_level = get_previous_level(current_level)  # B1 → A2
    adjustment = "decrease"
else:
    # 表现适中，保持当前难度
    suggested_level = current_level
    adjustment = "maintain"
```

**调整逻辑：**
- 分数 >= 80：提升CEFR等级
- 分数 < 60：降低CEFR等级
- 60-80：保持当前等级

### 阶段6：选择适配主题

**代码位置：** `config/topics.py` - `get_topics_by_level()`

```python
# 根据CEFR等级获取主题池
available_topics = self.topic_pool.get_topics_by_level("B1")

# 返回主题列表：
[
    {
        "name": "环保生活",
        "description": "Environmental protection and sustainable living",
        "cefr_level": "B1",
        "keywords": ["environment", "green", "sustainable"]
    },
    {
        "name": "工作与职业",
        "description": "Work, career, and professional development",
        "cefr_level": "B1",
        "keywords": ["work", "career", "job"]
    },
    ...
]
```

**主题池结构：**
- A1级：自我介绍、日常活动、食物偏好
- A2级：周末计划、旅行经历、兴趣爱好
- B1级：环保生活、工作与职业、健康生活
- B2级：人工智能影响、教育系统、全球化
- C1级：经济与政策、科技伦理
- C2级：哲学思辨、复杂社会问题

### 阶段7：生成下一题（核心）

**代码位置：** `services/generator.py` - `generate_question()`

#### 7.1 构建生成提示词

**代码位置：** `prompts/builders.py` - `build_generation_prompt()`

```python
messages = [
    {
        "role": "system",
        "content": "你是一个名为'LinguaCoach'的智能英语对话测评系统..."
    },
    {
        "role": "user",
        "content": """
        [当前用户能力画像]
        - CEFR等级: B1
        - 综合分数: 72.5/100
        - 强项: 基本表达流畅
        - 弱项: 语法准确性
        
        [可用主题池]
        - 环保生活 (CEFR: B1): Environmental protection...
        - 工作与职业 (CEFR: B1): Work, career...
        - 健康生活 (CEFR: B1): Health, fitness...
        
        [出题任务]
        请从上述主题池中，选择一个最适合该水平用户的主题，
        生成一个对话提示或问题。
        
        要求：
        1. 问题难度需精准匹配其CEFR等级（B1）
        2. 可适当针对其弱项（语法准确性）设计
        3. 问题需用英文提出，可包含少量中文解释
        4. 目标是引发用户3-5句话的、有内容的回答
        5. 问题应自然、有趣，能激发用户表达
        """
    }
]
```

#### 7.2 LLM生成题目

**代码位置：** `services/llm.py` - `chat_completion()`

```python
# 调用LLM生成题目
question = self.llm_service.chat_completion(
    messages=messages,
    temperature=0.8  # 较高温度增加多样性
)
```

**LLM生成示例：**
```
How do you think we can protect the environment in our daily life? 
(你认为我们在日常生活中如何保护环境？)
```

**生成策略：**
- **温度0.8**：增加问题多样性，避免重复
- **主题选择**：LLM从主题池中选择最合适的主题
- **难度匹配**：基于CEFR等级和用户画像
- **针对性**：可针对弱项设计（如语法准确性）

#### 7.3 话题引出机制

**话题引出的关键要素：**

1. **主题池引导**
   - 提供多个同等级主题供LLM选择
   - LLM根据用户画像选择最合适的主题

2. **上下文连贯性**
   - 考虑对话历史，避免重复话题
   - 自然过渡到新话题

3. **难度适配**
   - 基于CEFR等级选择主题
   - 根据用户表现动态调整

4. **个性化设计**
   - 针对用户弱项设计问题
   - 激发用户表达兴趣

**示例流程：**

```
第1轮：
用户: "I am a student."
系统: "Can you tell me about your hobbies?" (A1级 - 兴趣爱好)

第2轮：
用户: "I like reading books."
评估: 72分, B1级
系统: "How do you think reading can help us learn English?" (B1级 - 教育相关)

第3轮：
用户: "Reading helps me learn new words..."
评估: 75分, B1级
系统: "What are your views on environmental protection?" (B1级 - 环保生活)
```

### 阶段8：存储并返回

**代码位置：** `core/conversation.py` - `process_user_response()`

```python
# 1. 添加生成的题目到对话历史
conversation.add_message(MessageRole.ASSISTANT, next_question)

# 2. 保存对话
self.conversation_repo.save(conversation)

# 3. 保存用户画像
self.user_repo.save(user_profile)

# 4. 返回结果
return conversation, assessment_result, next_question
```

## 三、关键设计点

### 1. 模型回答的生成

**不是传统对话式回答，而是：**
- **评估结果**：LLM作为评估者，给出评分和评语
- **题目生成**：LLM作为出题者，生成适配问题

**两个LLM调用：**
1. **评估调用**（低温度0.3）：
   - 输入：对话历史 + 用户回答
   - 输出：JSON格式的评估结果
   - 目的：客观、一致地评估用户能力

2. **生成调用**（高温度0.8）：
   - 输入：用户画像 + 主题池
   - 输出：自然语言问题
   - 目的：生成多样、有趣的问题

### 2. 话题引出的策略

**多层次话题选择：**

1. **CEFR等级匹配**
   - 根据用户能力选择对应等级的主题

2. **主题池引导**
   - 提供多个候选主题
   - LLM选择最合适的主题

3. **对话连贯性**
   - 考虑对话历史
   - 自然过渡话题

4. **个性化适配**
   - 针对用户弱项
   - 激发表达兴趣

### 3. 动态自适应

**IRT理论应用：**
- 表现好（>=80分）→ 提升难度
- 表现差（<60分）→ 降低难度
- 表现中（60-80分）→ 保持难度

**实现方式：**
- 通过提示词工程实现
- 无需训练机器学习模型
- 完全基于LLM的指令遵循能力

## 四、完整示例

### 示例：3轮对话流程

**第1轮：**

```
用户输入: "I am a student. 我喜欢读书。"

[评估阶段]
LLM评估 → {
    overall_score: 72.5,
    cefr_level: "B1",
    strengths: ["基本表达流畅"],
    weaknesses: ["语法准确性"]
}

[自适应调整]
当前B1级，72.5分 → 保持B1难度

[主题选择]
从B1主题池选择 → "教育系统"

[生成题目]
LLM生成 → "How do you think reading can help us learn English? 
(你认为阅读如何帮助我们学习英语？)"

返回给用户
```

**第2轮：**

```
用户输入: "Reading helps me learn new words and improve my grammar."

[评估阶段]
LLM评估 → {
    overall_score: 78.0,
    cefr_level: "B1",
    strengths: ["词汇丰富", "表达流畅"],
    weaknesses: ["复杂句式"]
}

[自适应调整]
当前B1级，78.0分 → 保持B1难度（接近提升阈值）

[主题选择]
从B1主题池选择 → "环保生活"

[生成题目]
LLM生成 → "What are your views on environmental protection? 
(你对环境保护有什么看法？)"

返回给用户
```

**第3轮：**

```
用户输入: "I think we should protect the environment. 
We can use less plastic and recycle more."

[评估阶段]
LLM评估 → {
    overall_score: 82.0,
    cefr_level: "B2",
    strengths: ["观点清晰", "表达流畅"],
    weaknesses: []
}

[自适应调整]
当前B1级，82.0分 → 提升到B2难度

[主题选择]
从B2主题池选择 → "人工智能影响"

[生成题目]
LLM生成 → "Discuss the impact of artificial intelligence on our daily life. 
(讨论人工智能对我们日常生活的影响。)"

返回给用户
```

## 五、代码位置总结

| 功能 | 代码位置 |
|------|---------|
| 接收用户回答 | `core/conversation.py:82` |
| 准备上下文 | `services/context.py:65` |
| 构建评估提示词 | `prompts/builders.py:25` |
| LLM评估 | `services/evaluator.py:35` |
| 更新用户画像 | `models/user.py:32` |
| 自适应调整 | `core/adaptation.py:15` |
| 选择主题 | `config/topics.py:47` |
| 构建生成提示词 | `prompts/builders.py:62` |
| LLM生成题目 | `services/generator.py:49` |
| 存储结果 | `core/conversation.py:129` |

## 六、关键提示词模板

### 评估提示词
位置：`prompts/templates.py:35`

### 生成提示词
位置：`prompts/templates.py:80`

这两个提示词是系统的核心，通过精心设计的提示词，LLM能够：
- 准确评估用户能力
- 生成适配的题目
- 自然引出话题





