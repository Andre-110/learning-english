# 系统工作流程详解

## 一、输入处理流程

### 1.1 文本输入流程

```
用户输入文本
    ↓
API接收 (api/main.py: respond_to_conversation)
    ↓
参数验证 (Pydantic模型验证)
    ↓
ConversationManager.process_user_response()
    ↓
添加到对话历史 (conversation.add_message)
    ↓
准备上下文消息 (ContextManagerService)
    ↓
传递给评估服务
```

**代码位置：**
- `api/main.py` - API端点接收
- `core/conversation.py` - 对话处理
- `models/conversation.py` - 消息存储

### 1.2 语音输入流程（待实现）

```
用户语音输入
    ↓
语音转文本 (ASR服务: Whisper/Speech-to-Text)
    ↓
文本预处理 (中英文混杂处理)
    ↓
转换为标准消息格式
    ↓
进入文本处理流程
```

**实现方案：**
- 使用OpenAI Whisper API或Google Speech-to-Text
- 在API层添加语音端点
- 预处理模块处理中英文混杂

## 二、数据存储流程

### 2.1 对话数据存储

```
对话消息
    ↓
Conversation对象 (models/conversation.py)
    ↓
ConversationRepository.save()
    ↓
MemoryRepository (内存存储)
    ↓
或 DatabaseRepository (数据库存储 - 待实现)
```

**存储内容：**
- 消息内容
- 消息角色（user/assistant/system）
- 时间戳
- 元数据（评估结果等）

**代码位置：**
- `storage/repository.py` - 存储接口
- `storage/impl/memory_repository.py` - 内存实现

### 2.2 用户画像存储

```
评估结果
    ↓
AssessmentResult (models/assessment.py)
    ↓
更新UserProfile (models/user.py)
    ↓
UserRepository.save()
    ↓
持久化存储
```

**存储内容：**
- 综合分数 (0-100)
- CEFR等级 (A1-C2)
- 强项列表
- 弱项列表
- 对话轮数
- 最后更新时间

## 三、回复生成流程

### 3.1 评估 → 生成循环

```
用户回答
    ↓
评估服务 (EvaluatorService.evaluate)
    ↓
LLM评估 (LLMService.chat_completion_json)
    ↓
解析评估结果 (AssessmentResult)
    ↓
更新用户画像 (UserProfile.update_from_assessment)
    ↓
生成下一题 (QuestionGeneratorService.generate_question)
    ↓
LLM生成题目 (LLMService.chat_completion)
    ↓
返回给用户
```

**代码位置：**
- `services/evaluator.py` - 评估服务
- `services/generator.py` - 题目生成服务
- `core/conversation.py` - 流程编排

### 3.2 提示词构建

```
用户能力画像
    ↓
PromptBuilder.build_generation_prompt()
    ↓
GenerationPrompt.render()
    ↓
组装完整提示词
    ↓
发送给LLM
```

**代码位置：**
- `prompts/builders.py` - 提示词构建器
- `prompts/templates.py` - 提示词模板

## 四、动态调整问题难度

### 4.1 IRT自适应逻辑

```
当前用户表现
    ↓
评估分数 (overall_score)
    ↓
AdaptationEngine.calculate_difficulty_adjustment()
    ↓
判断调整方向:
  - 分数 >= 80 → 提升难度
  - 分数 < 60 → 降低难度
  - 60-80 → 保持当前难度
    ↓
选择CEFR等级
    ↓
从TopicPool选择适配主题
    ↓
生成匹配难度的问题
```

**代码位置：**
- `core/adaptation.py` - 自适应引擎
- `config/topics.py` - 主题池（按CEFR分级）

### 4.2 难度调整示例

```python
# 用户表现优秀 (85分, B1级)
→ 建议提升到 B2级
→ 选择B2级主题（如"人工智能影响"）
→ 生成B2难度问题

# 用户表现不佳 (55分, B1级)
→ 建议降低到 A2级
→ 选择A2级主题（如"周末计划"）
→ 生成A2难度问题
```

## 五、能力评估流程

### 5.1 多维度评估

```
用户回答文本
    ↓
构建评估提示词 (EvaluationPrompt)
    ↓
包含对话历史上下文
    ↓
LLM评估 (JSON格式输出)
    ↓
解析评估结果:
  - 内容相关性 (1-5分)
  - 语言准确性 (1-5分)
  - 表达流利度 (1-5分)
  - 交互深度 (1-5分)
    ↓
综合计算能力画像:
  - 综合分数 (0-100)
  - CEFR等级推断
  - 强项识别
  - 弱项识别
```

**代码位置：**
- `services/evaluator.py` - 评估服务
- `prompts/templates.py` - 评估提示词模板
- `models/assessment.py` - 评估结果模型

### 5.2 评估提示词结构

```
[系统角色设定]
你是专业的英语语言教师

[对话历史]
显示最近10轮对话

[当前用户回答]
用户本轮回答

[评估任务]
从4个维度评分 + 更新能力画像

[输出要求]
JSON格式输出
```

## 六、语音输入接入

### 6.1 实现方案

**方案1：使用OpenAI Whisper API（推荐）**

```python
# 在services/中添加speech.py
class SpeechService:
    def transcribe_audio(self, audio_file) -> str:
        # 调用Whisper API
        # 返回文本
        pass
```

**方案2：使用Google Speech-to-Text**

**方案3：使用本地Whisper模型**

### 6.2 API端点设计

```python
@app.post("/conversations/{conversation_id}/respond-audio")
async def respond_with_audio(
    conversation_id: str,
    audio_file: UploadFile,
    speech_service: SpeechService = Depends(get_speech_service)
):
    # 1. 转文本
    text = speech_service.transcribe_audio(audio_file)
    
    # 2. 处理中英文混杂
    processed_text = process_mixed_language(text)
    
    # 3. 进入正常流程
    return process_response(conversation_id, processed_text)
```

## 七、中英文混杂处理

### 7.1 处理策略

**策略1：在评估提示词中明确说明**

```
评估提示词中包含：
"注意：用户可能使用中英文混合回答，这是正常的语言学习现象。
请评估其英文部分的准确性，中文部分作为辅助理解。"
```

**策略2：文本预处理**

```python
def process_mixed_language(text: str) -> dict:
    """
    处理中英文混杂文本
    返回: {
        "english_parts": [...],
        "chinese_parts": [...],
        "mixed_analysis": {...}
    }
    """
    # 识别中英文部分
    # 分析混合使用是否恰当
    pass
```

**策略3：在评估维度中单独评估**

```
评估维度：
- 语言准确性（包括中英文混合使用的恰当性）
```

**当前实现：**
- 在`EvaluationPrompt`中已包含中英文混合评估说明
- LLM会自动识别和处理中英文混杂

## 八、用户画像更新

### 8.1 更新流程

```
每轮评估结果
    ↓
AssessmentResult.ability_profile
    ↓
UserProfile.update_from_assessment()
    ↓
更新字段:
  - overall_score (综合分数)
  - cefr_level (CEFR等级)
  - strengths (强项列表)
  - weaknesses (弱项列表)
  - conversation_count (轮数+1)
  - last_updated (更新时间)
    ↓
UserRepository.save()
    ↓
持久化存储
```

**代码位置：**
- `models/user.py` - UserProfile.update_from_assessment()
- `core/conversation.py` - 更新调用

### 8.2 画像累积更新

```
第1轮: 60分, A2级 → 初始画像
第2轮: 65分, A2级 → 更新分数和等级
第3轮: 70分, B1级 → 等级提升，更新强项
...
第N轮: 综合所有历史表现 → 最终画像
```

## 九、长期存储方案

### 9.1 当前实现（内存存储）

```
数据存储在内存中
    ↓
服务重启后数据丢失
    ↓
适合开发和测试
```

### 9.2 数据库存储（待实现）

**方案1：PostgreSQL**

```python
# storage/impl/postgres_repository.py
class PostgresConversationRepository(ConversationRepository):
    def __init__(self, connection_string):
        self.db = create_connection(connection_string)
    
    def save(self, conversation: Conversation):
        # 序列化为JSON存储
        # 或使用关系型表结构
        pass
```

**方案2：MongoDB**

```python
# storage/impl/mongo_repository.py
class MongoConversationRepository(ConversationRepository):
    def __init__(self, mongo_client):
        self.db = mongo_client.lingua_coach
    
    def save(self, conversation: Conversation):
        # 直接存储Pydantic模型（自动序列化）
        self.db.conversations.insert_one(conversation.dict())
```

**方案3：Redis（缓存+持久化）**

```python
# storage/impl/redis_repository.py
class RedisConversationRepository(ConversationRepository):
    def save(self, conversation: Conversation):
        # Redis存储（可设置过期时间）
        # 定期同步到数据库
        pass
```

### 9.3 存储结构设计

**对话表 (conversations)**
- conversation_id (主键)
- user_id (外键)
- messages (JSON数组)
- summary (文本)
- state (枚举)
- created_at (时间戳)
- updated_at (时间戳)

**用户表 (user_profiles)**
- user_id (主键)
- overall_score (浮点数)
- cefr_level (枚举)
- strengths (JSON数组)
- weaknesses (JSON数组)
- conversation_count (整数)
- last_updated (时间戳)

**评估表 (assessments)**
- assessment_id (主键)
- conversation_id (外键)
- round_number (整数)
- dimension_scores (JSON)
- ability_profile (JSON)
- timestamp (时间戳)

## 十、完整数据流示例

```
1. 用户输入: "I am a student. 我喜欢读书。"
   ↓
2. 文本预处理: 识别中英文混杂
   ↓
3. 添加到对话历史
   ↓
4. 构建评估提示词（包含对话历史）
   ↓
5. LLM评估:
   - 内容相关性: 4分
   - 语言准确性: 3.5分（中英文混合使用恰当）
   - 表达流利度: 4分
   - 交互深度: 3分
   ↓
6. 更新用户画像:
   - overall_score: 72分
   - cefr_level: B1
   - strengths: ["基本表达流畅"]
   - weaknesses: ["语法准确性"]
   ↓
7. 自适应调整:
   - 当前B1级，72分
   - 保持B1难度
   - 选择B1主题（如"环保生活"）
   ↓
8. 生成下一题:
   "How do you think we can protect the environment in our daily life?"
   ↓
9. 存储:
   - 对话消息 → ConversationRepository
   - 用户画像 → UserRepository
   - 评估结果 → 保存在消息元数据中
   ↓
10. 返回给用户
```

## 十一、运行Demo测试

详见 `DEMO.md` 文件。

