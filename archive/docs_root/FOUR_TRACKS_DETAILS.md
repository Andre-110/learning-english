# 四轨并行架构详解

## 一、评估轨如何保证 JSON 输出

### 1. Prompt 层面约束

```python
# prompts/templates.py - get_evaluation_user_prompt()

## Output Format (Strict JSON) - CRITICAL: Put response-related fields FIRST for streaming!
{
    "translation_zh": "用户话语的中文翻译（供UI显示）",
    "transcription": "exact user speech, preserving errors and Chinese",
    "evaluation": {
        "overall_score": <0-100>,
        "cefr_level": "<A1/A2/B1/B2/C1/C2>",
        ...
    },
    "interests": ["extracted topics"]
}
```

### 2. 后端解析容错

```python
# services/unified_processor.py - ResponseParser.parse()

def parse(response_text: str, transcription: str = "") -> ProcessingResult:
    # 1. 先尝试直接解析 JSON
    try:
        parsed = json.loads(fixed_text)
    except json.JSONDecodeError:
        # 2. 失败则用正则提取 JSON 部分
        json_match = re.search(r'\{[\s\S]*\}', fixed_text)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            # 3. 再失败则用正则提取各个字段
            result.evaluation = ResponseParser._extract_evaluation(response_text)
```

### 3. 重试机制（新增）

```python
# services/unified_processor.py - evaluate_only()

def evaluate_only(self, transcription, ..., max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            response = self.api_service.call_with_text(...)
            result = self.parser.parse(response)
            
            # 验证关键字段存在
            if result.evaluation and result.evaluation.get("overall_score") is not None:
                return result.evaluation
            
            # 缺少关键字段，重试
            if attempt < max_retries:
                logger.warning(f"评估结果缺少关键字段，重试 {attempt + 1}/{max_retries}")
                continue
        except json.JSONDecodeError:
            # JSON 解析失败，重试
            continue
    
    # 最终失败，返回默认值
    return default_result
```

---

## 二、四轨 Prompt 设计

### 1. 交互轨 Prompt

**目标**：低延迟、纯英文、自然对话

```python
# get_interaction_system_prompt(user_profile)

# Role: Your Direct Voice Partner
You are a warm, supportive English speaking partner.

## Voice Persona (Acoustic Guidelines)
1. **Tone**: Warm, energetic, and encouraging.
2. **Prosody**: Use natural intonation.
3. **Pacing**: Speak at a {moderate/natural} pace suitable for {level} learners.
4. **Verbal Fillers**: Use natural fillers (e.g., "Hmm," "Oh," "Well,").
5. **Emotion Mirroring**: Match the user's energy.
6. **No Robot-Talk**: Be expressive!

## Interaction Rules
1. **English ONLY**: Do not speak any Chinese.
2. **Brevity**: Keep responses under 20 words.
3. **Handle Silence/Noise**: If unclear, say: "Sorry, I didn't catch that."
4. **No Teaching Mode**: Don't correct errors explicitly.

## Target User
- Level: {cefr_level}
- Interests: {interests}
```

### 2. 转录轨 Prompt

**目标**：精确转录，保留错误

```python
# get_transcription_system_prompt()

You are a precise speech transcriber.

## Rules
1. **Zero Autocorrect**: Write EXACTLY what you hear. 
   If user says "I goes", write "I goes", NOT "I go".
2. **Preserve Chinese**: Write Chinese words as 汉字 (not pinyin).
3. **Preserve Fillers**: Keep "um", "uh", "like" etc.
4. **No Interpretation**: Do not add punctuation that changes meaning.

Output: Exact transcription only, nothing else.
```

### 3. 翻译轨 Prompt

**目标**：快速英译中

```python
# get_translation_system_prompt()

You are a translator. Translate English to natural Chinese.

Rules:
1. Translate naturally, not word-by-word
2. Keep the tone and emotion
3. Output Chinese ONLY, no explanations

# get_translation_user_prompt(english_text)

Translate to Chinese:
"{english_text}"

Output: Chinese translation only.
```

### 4. 评估轨 Prompt

**目标**：多维度评估，JSON 输出

```python
# get_evaluation_system_prompt()

You are a Linguistic Auditor. Analyze the user's speech.

## Evaluation Dimensions
1. Grammar: Tense, sentence structure, subject-verb agreement, articles, prepositions.
2. Vocabulary: Word choice, collocations, idioms, Chinese-to-English accuracy.
3. Prosody: Sentence stress, intonation, rhythm, confidence indicator.
4. Fluency: Filler words, unnatural pauses, repetitions.
5. Coherence: Logical connectors, topic relevance, idea completeness.

## CEFR Scoring Standards (Few-Shot Examples)
- [A1, Score 15-25]: "I... want... go 足球." → Fragmented, used Chinese.
- [A2, Score 30-40]: "Yesterday I go to school." → Simple sentence, tense error.
- [B1, Score 50-60]: "I think this movie is interesting." → Clear but basic.
- [B2, Score 70-80]: "If I were you, I would've taken that." → Correct conditionals.
- [C1, Score 85-92]: "The proliferation of AI has precipitated..." → Academic vocabulary.

## Critical Rules
1. **Zero Autocorrect**: Preserve all errors.
2. **Top 2 Errors Only**: Don't overwhelm the user.
3. **Positive First**: Always include at least 1 good expression.

# get_evaluation_user_prompt(transcription, conversation_history, user_profile)

## Current Input
User said: "{transcription}"

## Output Format (Strict JSON)
{
    "translation_zh": "中文翻译",
    "transcription": "exact user speech",
    "evaluation": {
        "overall_score": <0-100>,
        "cefr_level": "<A1-C2>",
        "prosody_feedback": "...",
        "corrections": [{"type": "...", "original": "...", "corrected": "...", "explanation": "..."}],
        "good_expressions": [{"expression": "...", "reason": "..."}],
        "encouragement": "..."
    },
    "interests": ["..."]
}
```

---

## 三、用户画像、评分、兴趣点的更新与存储

### 0. 完整数据流图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              用户画像数据流                                      │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────┐
                              │  新用户注册  │
                              └──────┬──────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           初始化用户画像                                         │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  存储位置: Supabase users 表                                                    │
│  初始值:                                                                        │
│    • overall_score: 0.0                                                        │
│    • cefr_level: A1                                                            │
│    • strengths: []                                                             │
│    • weaknesses: []                                                            │
│    • interests: []                                                             │
│    • conversation_count: 0                                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           开始新会话                                            │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  触发: 前端 startConversation()                                                 │
│  操作:                                                                          │
│    1. 从 users 表加载用户画像                                                   │
│    2. 将画像传入 WebSocket 连接                                                 │
│    3. 画像用于生成个性化初始问候语                                               │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           对话轮次循环                                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
        ▼                            ▼                            ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│    交互轨          │    │    转录轨          │    │    评估轨          │
│ ───────────────── │    │ ───────────────── │    │ ───────────────── │
│ 读取:             │    │ 输出:             │    │ 读取:             │
│ • cefr_level      │    │ • transcription   │    │ • cefr_level      │
│ • interests       │    │                   │    │ • conversation_   │
│                   │    │                   │    │   history         │
│ 用途:             │    │                   │    │                   │
│ • 调整语速        │    │                   │    │ 输出:             │
│ • 话题相关性      │    │                   │    │ • overall_score   │
│                   │    │                   │    │ • corrections     │
│                   │    │                   │    │ • interests (新)  │
└───────────────────┘    └───────────────────┘    └───────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        保存轮次数据到 messages 表                                │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  存储:                                                                          │
│    messages.metadata = {                                                        │
│      "evaluation": {                                                            │
│        "overall_score": 75,                                                     │
│        "cefr_level": "B1",                                                      │
│        "corrections": [...],                                                    │
│        "good_expressions": [...]                                                │
│      }                                                                          │
│    }                                                                            │
│  用途: 前端展示评估卡片、历史回顾                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ (循环多轮)
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           会话结束 (WebSocket 断开)                              │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
        ▼                            ▼                            ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│ 计算会话平均分     │    │ 更新 conversations │    │ 更新 users 表     │
│ ───────────────── │    │ ───────────────── │    │ ───────────────── │
│                   │    │                   │    │                   │
│ session_avg =     │    │ overall_score =   │    │ 加权平均:         │
│   sum(scores)     │    │   session_avg     │    │ new = old*0.7 +   │
│   / len(scores)   │    │                   │    │       session*0.3 │
│                   │    │ cefr_level =      │    │                   │
│                   │    │   final_level     │    │ cefr_level =      │
│                   │    │                   │    │   score_to_cefr() │
│                   │    │ state =           │    │                   │
│                   │    │   "completed"     │    │ interests +=      │
│                   │    │                   │    │   new_interests   │
└───────────────────┘    └───────────────────┘    └───────────────────┘
        │                            │                            │
        │                            ▼                            ▼
        │                 ┌───────────────────┐    ┌───────────────────┐
        │                 │ 侧边栏显示        │    │ 头像旁显示        │
        │                 │ 会话评分          │    │ 用户整体评分      │
        │                 └───────────────────┘    └───────────────────┘
        │
        └─────────────────────────────────────────────────────────────┐
                                                                      │
                                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           前端刷新用户画像                                       │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  触发: WebSocket onclose 事件                                                   │
│  操作: loadUserProfile() → GET /users/{user_id}/profile                         │
│  更新: userProfile.value = { overall_score, cefr_level, interests, ... }        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 兴趣点数据流（会话结束时更新）

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              兴趣点数据流                                        │
│                          ⚠️ 会话结束时批量更新                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                           轮次 1: 用户语音输入                                   │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  用户: "I really love playing basketball on weekends"                           │
│  评估轨输出: { "interests": ["basketball", "sports"] }                          │
│  收集到: session_interests = ["basketball", "sports"]                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           轮次 2: 用户语音输入                                   │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  用户: "I also enjoy traveling to Japan"                                        │
│  评估轨输出: { "interests": ["travel", "Japan"] }                               │
│  收集到: session_interests = ["basketball", "sports", "travel", "Japan"]        │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           轮次 3: 用户语音输入                                   │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  用户: "Music helps me relax after work"                                        │
│  评估轨输出: { "interests": ["music", "relaxation"] }                           │
│  收集到: session_interests = ["basketball", "sports", "travel", "Japan",        │
│                               "music", "relaxation"]                            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     会话结束 (WebSocket 断开)                                    │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  代码位置: api/openrouter_audio_endpoint.py - audio_chat() finally 块           │
│                                                                                 │
│  合并逻辑:                                                                      │
│    existing_interests = ["cooking", "movies"]  # 用户历史兴趣                   │
│    session_interests = ["basketball", "sports", "travel", "Japan",              │
│                         "music", "relaxation"]                                  │
│                                                                                 │
│    all_interests = dedupe(existing + session)[-10:]                             │
│    # 结果: ["cooking", "movies", "basketball", "sports", "travel",              │
│    #        "Japan", "music", "relaxation"]                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           存储到数据库                                           │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  代码位置: storage/impl/supabase_repository.py - SupabaseUserRepository.save()  │
│                                                                                 │
│  存储格式:                                                                      │
│    users.metadata = {                                                           │
│      "interests": [                                                             │
│        {"category": "general", "tags": ["cooking"], "weight": 1.0},             │
│        {"category": "general", "tags": ["movies"], "weight": 1.0},              │
│        {"category": "general", "tags": ["basketball"], "weight": 1.0},          │
│        ...                                                                      │
│      ]                                                                          │
│    }                                                                            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           下次对话时调用                                         │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  代码位置: prompts/templates.py - get_interaction_system_prompt()               │
│                                                                                 │
│  加载:                                                                          │
│    interests = user_profile.get('interests', [])                                │
│    interests_str = ', '.join(interests[:5])                                     │
│    # 结果: "cooking, movies, basketball, sports, travel"                        │
│                                                                                 │
│  注入 Prompt:                                                                   │
│    """                                                                          │
│    ## Target User                                                               │
│    - Level: B1                                                                  │
│    - Interests: cooking, movies, basketball, sports, travel                     │
│    """                                                                          │
│                                                                                 │
│  效果:                                                                          │
│    AI 会根据用户兴趣调整话题，例如:                                              │
│    "Oh, you like basketball! Did you catch any games this weekend?"             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 评分更新数据流

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              评分更新数据流                                      │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                           轮次 1                                                │
│  用户: "Yesterday I go to school"                                               │
│  评估: { overall_score: 45, cefr_level: "A2" }                                  │
│  存储: messages.metadata.evaluation                                             │
│  展示: 评估卡片 (45分, A2)                                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           轮次 2                                                │
│  用户: "I went to the park with my friends"                                     │
│  评估: { overall_score: 65, cefr_level: "B1" }                                  │
│  存储: messages.metadata.evaluation                                             │
│  展示: 评估卡片 (65分, B1)                                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           轮次 3                                                │
│  用户: "If I had known, I would have come earlier"                              │
│  评估: { overall_score: 78, cefr_level: "B2" }                                  │
│  存储: messages.metadata.evaluation                                             │
│  展示: 评估卡片 (78分, B2)                                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           会话结束                                               │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  session_scores = [45, 65, 78]                                                  │
│  session_avg = (45 + 65 + 78) / 3 = 62.67                                       │
│  session_level = "B2" (最后一轮)                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
                                     │
        ┌────────────────────────────┴────────────────────────────┐
        │                                                         │
        ▼                                                         ▼
┌───────────────────────────────────┐    ┌───────────────────────────────────┐
│      更新 conversations 表         │    │      更新 users 表                 │
│ ───────────────────────────────── │    │ ───────────────────────────────── │
│                                   │    │                                   │
│ UPDATE conversations SET          │    │ 假设用户历史分数: 55.0            │
│   overall_score = 62.67,          │    │                                   │
│   cefr_level = "B2",              │    │ 新分数 = 55.0 * 0.7 + 62.67 * 0.3 │
│   state = "completed"             │    │        = 38.5 + 18.8              │
│ WHERE conversation_id = ?         │    │        = 57.3                     │
│                                   │    │                                   │
│ 展示: 侧边栏                       │    │ UPDATE users SET                  │
│ ┌─────────────────────────┐       │    │   overall_score = 57.3,           │
│ │ 📝 对话 1    62.7 B2    │       │    │   cefr_level = "B1"               │
│ │ 📝 对话 2    45.0 A2    │       │    │ WHERE user_id = ?                 │
│ │ 📝 对话 3    78.5 B2    │       │    │                                   │
│ └─────────────────────────┘       │    │ 展示: 头像旁                       │
│                                   │    │ ┌─────────────────────────┐       │
│                                   │    │ │ 👤 用户名  57.3 B1      │       │
│                                   │    │ └─────────────────────────┘       │
└───────────────────────────────────┘    └───────────────────────────────────┘
```

---

### 1. 数据模型

```python
# models/user.py

class UserProfile:
    user_id: str
    overall_score: float        # 用户整体评分 (0-100)
    cefr_level: CEFRLevel       # CEFR 等级 (A1-C2)
    strengths: List[str]        # 强项
    weaknesses: List[str]       # 弱项
    interests: List[InterestTag]  # 兴趣标签
    conversation_count: int     # 对话次数

class InterestTag:
    category: str               # 分类 (e.g., "sports", "technology")
    tags: List[str]             # 具体标签 (e.g., ["basketball", "football"])
    weight: float               # 权重 (越高越感兴趣)
    last_discussed: str         # 最后讨论时间
```

### 2. 存储位置

| 数据 | 存储表 | 字段 |
|------|--------|------|
| 用户画像 | `users` | `overall_score`, `cefr_level`, `strengths`, `weaknesses` |
| 兴趣点 | `users.metadata` | `interests` (JSON 数组) |
| 轮次评分 | `messages.metadata` | `evaluation` (JSON) |
| 会话评分 | `conversations` | `overall_score`, `cefr_level` |

### 3. 更新时机

```
┌─────────────────────────────────────────────────────────────┐
│                  轮次评分 (Round Score)                      │
│  ─────────────────────────────────────────────────────────  │
│  来源: 评估轨 evaluation.overall_score                       │
│  时机: 每轮对话结束                                          │
│  存储: messages.metadata.evaluation                         │
│  展示: 评估卡片                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 平均
┌─────────────────────────────────────────────────────────────┐
│                  会话评分 (Session Score)                    │
│  ─────────────────────────────────────────────────────────  │
│  计算: sum(session_scores) / len(session_scores)            │
│  时机: 会话结束 (WebSocket 断开)                             │
│  存储: conversations.overall_score                          │
│  展示: 侧边栏对话列表                                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 加权平均
┌─────────────────────────────────────────────────────────────┐
│                  用户评分 (User Score)                       │
│  ─────────────────────────────────────────────────────────  │
│  计算: old_score * 0.7 + session_score * 0.3                │
│  时机: 会话结束                                              │
│  存储: users.overall_score                                  │
│  展示: 用户头像旁边                                          │
└─────────────────────────────────────────────────────────────┘
```

### 4. 更新代码

```python
# api/openrouter_audio_endpoint.py - audio_chat() finally 块

# 1. 计算本次会话的平均分
session_avg_score = sum(session_scores) / len(session_scores)

# 2. 更新 conversations 表
conv_repo.client.table("conversations").update({
    "cefr_level": session_final_level,
    "overall_score": round(session_avg_score, 2),
    "state": "completed"
}).eq("conversation_id", conversation_id).execute()

# 3. 更新用户画像（加权平均）
old_score = db_profile.overall_score or 50.0
new_score = (old_score * 0.7) + (session_avg_score * 0.3)
db_profile.overall_score = round(new_score, 1)
db_profile.cefr_level = score_to_cefr(new_score)
user_repo.save(db_profile)
```

### 5. 兴趣点提取与利用

**提取**（评估轨 Prompt 中）：
```json
{
    "interests": ["basketball", "AI", "travel"]
}
```

**存储**：
```python
# storage/impl/supabase_repository.py - SupabaseUserRepository.save()

interests_data = []
for interest in user_profile.interests:
    interests_data.append({
        "category": interest.category,
        "tags": interest.tags,
        "weight": interest.weight,
        "last_discussed": interest.last_discussed
    })
user_data["metadata"]["interests"] = interests_data
```

**利用**（交互轨 Prompt 中）：
```python
# prompts/templates.py - get_interaction_system_prompt()

interests = user_profile.get('interests', [])
interests_str = ', '.join(interests[:5])

return f"""
## Target User
- Level: {level}
- Interests: {interests_str}
"""
```

### 6. 上下文压缩

当前实现：**保留最近 10 轮对话**

```python
# api/openrouter_audio_endpoint.py - process_audio_stream()

# 保留最近 10 轮
if len(conversation_history) > 20:
    conversation_history[:] = conversation_history[-20:]
```

**Prompt 中使用**：
```python
# prompts/templates.py - get_evaluation_user_prompt()

if conversation_history and len(conversation_history) > 0:
    recent = conversation_history[-4:]  # 只取最近 4 条
    for msg in recent:
        role = "User" if msg.get('role') == 'user' else "Coach"
        content = msg.get('content', '')[:100]  # 截断到 100 字符
        lines.append(f"{role}: {content}")
```

**未来优化方向**：
- 使用 LLM 生成对话摘要（`conversation.summary`）
- 基于摘要 + 最近几轮构建上下文
- 根据话题相关性动态选择历史消息

---

## 四、前端翻译处理

### 1. Store 层处理

```javascript
// frontend/src/stores/conversation.js - handleWebSocketMessage()

case 'translation':
  // AI 回复的中文翻译 - 关联到当前 AI 消息
  if (currentAssistantMessageId !== null) {
    const assistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
    if (assistantMsg) {
      assistantMsg.translation = data.text
    }
  }
  break
```

### 2. 组件层展示

```vue
<!-- frontend/src/components/ConversationPanel.vue -->

<!-- AI 消息的中文翻译 -->
<div v-if="message.role === 'assistant' && message.translation" class="translation-inline">
  <span class="translation-label">🇨🇳</span>
  <span class="translation-text">{{ message.translation }}</span>
</div>
```

### 3. 样式

```css
.translation-inline {
  margin-left: 48px;
  padding: 8px 12px;
  background: rgba(66, 153, 225, 0.08);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--primary);
  font-size: 0.85rem;
  color: var(--text-secondary);
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
```

### 4. 效果

```
┌─────────────────────────────────────────┐
│ 🤖  That's interesting! Tell me more   │
│     about your weekend plans.           │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│ 🇨🇳 真有趣！跟我多说说你的周末计划吧。    │
└─────────────────────────────────────────┘
```

