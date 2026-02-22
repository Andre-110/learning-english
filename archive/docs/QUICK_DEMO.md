# 快速Demo测试指南

## 一、系统工作流程总览

### 1. 输入处理流程

```
用户输入（文本/语音）
    ↓
API接收 (api/main.py 或 api/speech_endpoint.py)
    ↓
参数验证 (Pydantic)
    ↓
ConversationManager.process_user_response()
    ↓
添加到对话历史
    ↓
准备上下文（包含摘要）
    ↓
进入评估流程
```

### 2. 数据存储流程

**对话数据：**
- 存储在 `Conversation` 对象中
- 通过 `ConversationRepository` 保存
- 当前使用内存存储（可扩展数据库）

**用户画像：**
- 存储在 `UserProfile` 对象中
- 通过 `UserRepository` 保存
- 每轮评估后自动更新

### 3. 回复生成流程

```
用户回答
    ↓
评估服务 (EvaluatorService)
    ↓
LLM评估 → JSON结果
    ↓
解析评估结果
    ↓
更新用户画像
    ↓
自适应调整难度
    ↓
生成下一题 (QuestionGeneratorService)
    ↓
返回给用户
```

### 4. 动态调整问题难度

**IRT自适应逻辑：**
- 分数 >= 80 → 提升难度（CEFR等级+1）
- 分数 < 60 → 降低难度（CEFR等级-1）
- 60-80 → 保持当前难度

**实现位置：**
- `core/adaptation.py` - AdaptationEngine
- `config/topics.py` - 按CEFR分级的主题池

### 5. 能力评估流程

**4个评估维度：**
1. 内容相关性（1-5分）
2. 语言准确性（1-5分）
3. 表达流利度（1-5分）
4. 交互深度（1-5分）

**综合评估：**
- 综合分数（0-100）
- CEFR等级推断（A1-C2）
- 强项识别
- 弱项识别

**实现位置：**
- `services/evaluator.py` - EvaluatorService
- `prompts/templates.py` - EvaluationPrompt

### 6. 语音输入接入

**实现方案：**
- 使用 OpenAI Whisper API
- 支持 mp3, wav, m4a 等格式
- 自动检测语言

**API端点：**
```
POST /conversations/{conversation_id}/respond-audio
```

**实现位置：**
- `services/speech.py` - WhisperService
- `api/speech_endpoint.py` - 语音API端点

### 7. 中英文混杂处理

**处理策略：**
1. **在评估提示词中说明** - 已实现
   - 提示词明确说明中英文混合是正常现象
   - LLM会评估英文部分的准确性

2. **文本预处理** - 已实现
   - `utils/text_processor.py` - 检测和分析中英文混杂
   - 规范化文本（添加空格）

3. **单独评估维度** - 已实现
   - "语言准确性（包括中英文混合使用的恰当性）"

### 8. 用户画像更新

**更新时机：**
- 每轮评估后自动更新

**更新内容：**
- overall_score（综合分数）
- cefr_level（CEFR等级）
- strengths（强项列表）
- weaknesses（弱项列表）
- conversation_count（轮数+1）
- last_updated（更新时间）

**实现位置：**
- `models/user.py` - UserProfile.update_from_assessment()
- `core/conversation.py` - 更新调用

### 9. 长期存储

**当前实现：**
- 内存存储（MemoryRepository）
- 服务重启后数据丢失

**扩展方案：**
- PostgreSQL（关系型数据库）
- MongoDB（文档数据库）
- Redis（缓存+持久化）

**存储结构：**
- conversations 表（对话数据）
- user_profiles 表（用户画像）
- assessments 表（评估历史）

## 二、运行Demo测试

### 步骤1：启动服务

```bash
# 确保已配置.env文件
cd /home/ubuntu/learning_english

# 启动服务
uvicorn api.main:app --reload
```

### 步骤2：运行文本Demo

```bash
# 在另一个终端运行
python demo_text.py
```

**预期输出：**
```
============================================================
 Demo: 文本对话流程
============================================================

1️⃣ 开始对话...
✅ 对话已开始
   对话ID: abc123-def456-ghi789
   初始问题: Can you tell me about yourself?

2️⃣ 第1轮回答
   用户输入: I am a student. 我喜欢读书。
   ✅ 评估结果:
      综合分数: 72.5/100
      CEFR等级: B1
      强项: 基本表达流畅
      弱项: 语法准确性
   📊 维度评分:
      内容相关性: 4.0/5 - 直接回答了问题
      语言准确性: 3.5/5 - 中英文混合使用恰当
      表达流利度: 4.0/5 - 句子通顺
      交互深度: 3.0/5 - 回答较为简单
   ❓ 下一题: What kind of books do you like to read?
   👤 用户画像:
      综合分数: 72.5/100
      CEFR等级: B1
      对话轮数: 1
```

### 步骤3：运行交互式测试

```bash
python test_client.py
```

### 步骤4：测试语音输入（可选）

```bash
# 准备音频文件
python demo_speech.py your_audio.mp3
```

或使用curl：

```bash
curl -X POST "http://localhost:8000/conversations/{conversation_id}/respond-audio" \
  -F "audio_file=@your_audio.mp3"
```

## 三、完整数据流示例

### 示例：中英文混杂回答

```
1. 用户输入: "I am a student. 我喜欢读书。"
   ↓
2. 文本预处理:
   - 检测到中英文混杂
   - 规范化: "I am a student. 我喜欢读书。"
   ↓
3. 添加到对话历史
   ↓
4. 构建评估提示词（包含对话历史）
   ↓
5. LLM评估:
   {
     "dimension_scores": [
       {"dimension": "内容相关性", "score": 4.0, "comment": "直接回答了问题"},
       {"dimension": "语言准确性", "score": 3.5, "comment": "中英文混合使用恰当"},
       {"dimension": "表达流利度", "score": 4.0, "comment": "句子通顺"},
       {"dimension": "交互深度", "score": 3.0, "comment": "回答较为简单"}
     ],
     "ability_profile": {
       "overall_score": 72.5,
       "cefr_level": "B1",
       "strengths": ["基本表达流畅"],
       "weaknesses": ["语法准确性"]
     }
   }
   ↓
6. 更新用户画像:
   - overall_score: 72.5
   - cefr_level: B1
   - strengths: ["基本表达流畅"]
   - weaknesses: ["语法准确性"]
   ↓
7. 自适应调整:
   - 当前B1级，72.5分
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

## 四、关键代码位置

### 输入处理
- `api/main.py` - 文本输入API
- `api/speech_endpoint.py` - 语音输入API
- `utils/text_processor.py` - 文本预处理

### 数据存储
- `storage/repository.py` - 存储接口
- `storage/impl/memory_repository.py` - 内存实现
- `models/conversation.py` - 对话模型
- `models/user.py` - 用户模型

### 评估与生成
- `services/evaluator.py` - 评估服务
- `services/generator.py` - 题目生成服务
- `prompts/templates.py` - 提示词模板

### 自适应调整
- `core/adaptation.py` - 自适应引擎
- `config/topics.py` - 主题池（按CEFR分级）

### 用户画像更新
- `models/user.py` - UserProfile.update_from_assessment()
- `core/conversation.py` - 更新调用

## 五、测试检查清单

- [ ] 服务启动成功
- [ ] 可以开始对话
- [ ] 可以回答问题
- [ ] 评估功能正常
- [ ] 中英文混杂处理正常
- [ ] 用户画像更新正常
- [ ] 难度自适应调整正常
- [ ] 题目生成正常
- [ ] 多轮对话连贯性正常
- [ ] 语音输入正常（如果启用）

## 六、常见问题

### Q1: 如何测试中英文混杂？
A: 在回答中使用中英文混合，如 "I am a student. 我喜欢读书。"

### Q2: 如何查看用户画像？
A: 每轮回答后，响应中包含 `user_profile` 字段

### Q3: 如何测试难度调整？
A: 连续回答多轮，观察分数变化和CEFR等级调整

### Q4: 语音输入支持哪些格式？
A: mp3, wav, m4a, webm 等常见音频格式

### Q5: 数据如何长期存储？
A: 当前使用内存存储，可扩展实现数据库存储（见 `storage/impl/`）

