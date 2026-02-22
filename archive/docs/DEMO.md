# Demo测试指南

## 一、准备工作

### 1.1 安装依赖

```bash
cd /home/ubuntu/learning_english
pip install -r requirements.txt
```

### 1.2 配置环境变量

创建`.env`文件：

```bash
cat > .env << EOF
OPENAI_API_KEY=your_openai_api_key_here
PRIMARY_LLM_MODEL=gpt-4
LLM_PROVIDER=openai
MAX_CONVERSATION_ROUNDS=20
CONTEXT_SUMMARY_INTERVAL=5
LOG_LEVEL=INFO
STORAGE_BACKEND=memory
EOF
```

### 1.3 启动服务

```bash
# 方式1：使用启动脚本
./start.sh

# 方式2：直接启动
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## 二、Demo测试脚本

### 2.1 基础文本对话Demo

创建 `demo_text.py`：

```python
#!/usr/bin/env python3
"""
基础文本对话Demo - 演示完整工作流程
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def print_section(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def demo_text_conversation():
    """演示文本对话流程"""
    
    print_section("Demo: 文本对话流程")
    
    # 1. 开始对话
    print("\n1️⃣ 开始对话...")
    response = requests.post(
        f"{BASE_URL}/conversations/start",
        json={"user_id": "demo_user_001"}
    )
    assert response.status_code == 200, f"开始对话失败: {response.status_code}"
    
    data = response.json()
    conversation_id = data["conversation_id"]
    print(f"✅ 对话已开始")
    print(f"   对话ID: {conversation_id}")
    print(f"   初始问题: {data['initial_question']}")
    
    # 2. 多轮对话
    test_responses = [
        "I am a student. 我喜欢读书。",  # 中英文混杂
        "I think reading can help us learn new things and improve our English.",
        "Yes, I read books every day. 我每天读30分钟。",
    ]
    
    for i, user_response in enumerate(test_responses, 1):
        print(f"\n{i+1}️⃣ 第{i}轮回答")
        print(f"   用户输入: {user_response}")
        
        # 发送回答
        response = requests.post(
            f"{BASE_URL}/conversations/{conversation_id}/respond",
            json={"user_response": user_response}
        )
        assert response.status_code == 200, f"回答失败: {response.status_code}"
        
        data = response.json()
        
        # 显示评估结果
        assessment = data["assessment"]
        profile = assessment["ability_profile"]
        
        print(f"   ✅ 评估结果:")
        print(f"      综合分数: {profile['overall_score']:.1f}/100")
        print(f"      CEFR等级: {profile['cefr_level']}")
        print(f"      强项: {', '.join(profile['strengths']) if profile['strengths'] else '无'}")
        print(f"      弱项: {', '.join(profile['weaknesses']) if profile['weaknesses'] else '无'}")
        
        # 显示维度评分
        print(f"   📊 维度评分:")
        for dim in assessment["dimension_scores"]:
            print(f"      {dim['dimension']}: {dim['score']:.1f}/5 - {dim['comment']}")
        
        # 显示下一题
        print(f"   ❓ 下一题: {data['next_question']}")
        
        # 显示用户画像更新
        user_profile = data["user_profile"]
        print(f"   👤 用户画像:")
        print(f"      综合分数: {user_profile['overall_score']:.1f}/100")
        print(f"      CEFR等级: {user_profile['cefr_level']}")
        print(f"      对话轮数: {user_profile['conversation_count']}")
        
        time.sleep(1)  # 避免请求过快
    
    # 3. 获取对话信息
    print(f"\n📋 获取对话信息...")
    response = requests.get(f"{BASE_URL}/conversations/{conversation_id}")
    assert response.status_code == 200
    
    data = response.json()
    print(f"   对话状态: {data['state']}")
    print(f"   总轮数: {data['round_count']}")
    
    print_section("Demo完成")
    return conversation_id

if __name__ == "__main__":
    try:
        demo_text_conversation()
    except Exception as e:
        print(f"\n❌ Demo失败: {e}")
        import traceback
        traceback.print_exc()
```

### 2.2 语音输入Demo

创建 `demo_speech.py`：

```python
#!/usr/bin/env python3
"""
语音输入Demo - 演示语音转文本功能
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def demo_speech_conversation(audio_file_path: str):
    """演示语音输入流程"""
    
    print("\n" + "=" * 60)
    print(" Demo: 语音输入流程")
    print("=" * 60)
    
    # 1. 开始对话
    print("\n1️⃣ 开始对话...")
    response = requests.post(
        f"{BASE_URL}/conversations/start",
        json={"user_id": "demo_user_speech"}
    )
    assert response.status_code == 200
    
    data = response.json()
    conversation_id = data["conversation_id"]
    print(f"✅ 对话已开始: {conversation_id}")
    
    # 2. 发送语音文件
    print(f"\n2️⃣ 发送语音文件: {audio_file_path}")
    with open(audio_file_path, "rb") as f:
        files = {"audio_file": f}
        response = requests.post(
            f"{BASE_URL}/conversations/{conversation_id}/respond-audio",
            files=files
        )
    
    if response.status_code != 200:
        print(f"❌ 语音处理失败: {response.status_code}")
        print(f"   错误: {response.text}")
        return
    
    data = response.json()
    
    # 显示转录结果
    print(f"✅ 语音转录成功")
    print(f"   转录文本: {data['transcribed_text']}")
    print(f"   规范化文本: {data['normalized_text']}")
    
    # 显示语言分析
    lang_analysis = data['language_analysis']
    print(f"   📊 语言分析:")
    print(f"      包含中文: {lang_analysis['has_chinese']}")
    print(f"      包含英文: {lang_analysis['has_english']}")
    print(f"      中英文混杂: {lang_analysis['is_mixed']}")
    if lang_analysis['is_mixed']:
        print(f"      中文比例: {lang_analysis['chinese_ratio']:.1%}")
        print(f"      英文比例: {lang_analysis['english_ratio']:.1%}")
    
    # 显示评估结果
    assessment = data['assessment']
    profile = assessment['ability_profile']
    print(f"   ✅ 评估结果:")
    print(f"      综合分数: {profile['overall_score']:.1f}/100")
    print(f"      CEFR等级: {profile['cefr_level']}")
    
    # 显示下一题
    print(f"   ❓ 下一题: {data['next_question']}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python demo_speech.py <audio_file_path>")
        print("示例: python demo_speech.py test_audio.mp3")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    try:
        demo_speech_conversation(audio_file)
    except Exception as e:
        print(f"\n❌ Demo失败: {e}")
        import traceback
        traceback.print_exc()
```

### 2.3 完整流程Demo

创建 `demo_full.py`：

```python
#!/usr/bin/env python3
"""
完整流程Demo - 演示所有功能
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def demo_full_workflow():
    """演示完整工作流程"""
    
    print("\n" + "=" * 70)
    print(" LinguaCoach 完整流程Demo")
    print("=" * 70)
    
    # ========== 阶段1: 初始化 ==========
    print("\n【阶段1】初始化对话")
    print("-" * 70)
    
    response = requests.post(
        f"{BASE_URL}/conversations/start",
        json={"user_id": "demo_full_001"}
    )
    data = response.json()
    conversation_id = data["conversation_id"]
    print(f"✅ 对话ID: {conversation_id}")
    print(f"📝 初始问题: {data['initial_question']}")
    
    # ========== 阶段2: 多轮对话 ==========
    print("\n【阶段2】多轮对话与评估")
    print("-" * 70)
    
    conversations = [
        {
            "input": "I am a student. 我喜欢读书。",
            "description": "中英文混杂回答
        },
        {
            "input": "I read books every day. It helps me learn English.",
            "response": "纯英文回答"
        },
        {
            "input": "Yes, I think reading is very important. 阅读可以开阔视野。",
            "response": "中英文混合回答"
        },
    ]
    
    for i, conv in enumerate(conversations, 1):
        print(f"\n--- 第{i}轮对话 ---")
        print(f"用户输入: {conv['input']}")
        print(f"输入类型: {conv['response']}")
        
        response = requests.post(
            f"{BASE_URL}/conversations/{conversation_id}/respond",
            json={"user_response": conv['input']}
        )
        data = response.json()
        
        # 显示评估
        assessment = data['assessment']
        profile = assessment['ability_profile']
        
        print(f"\n📊 评估结果:")
        print(f"   综合分数: {profile['overall_score']:.1f}/100")
        print(f"   CEFR等级: {profile['cefr_level']}")
        print(f"   强项: {', '.join(profile['strengths']) if profile['strengths'] else '无'}")
        print(f"   弱项: {', '.join(profile['weaknesses']) if profile['weaknesses'] else '无'}")
        
        # 显示维度评分
        print(f"\n📈 维度评分:")
        for dim in assessment['dimension_scores']:
            print(f"   {dim['dimension']}: {dim['score']:.1f}/5")
            print(f"      评语: {dim['comment']}")
        
        # 显示自适应调整
        user_profile = data['user_profile']
        print(f"\n🎯 难度调整:")
        print(f"   当前等级: {user_profile['cefr_level']}")
        print(f"   当前分数: {user_profile['overall_score']:.1f}/100")
        
        # 显示下一题
        print(f"\n❓ 下一题:")
        print(f"   {data['next_question']}")
        
        time.sleep(1)
    
    # ========== 阶段3: 查看最终状态 ==========
    print("\n【阶段3】最终状态")
    print("-" * 70)
    
    response = requests.get(f"{BASE_URL}/conversations/{conversation_id}")
    data = response.json()
    
    print(f"对话状态: {data['state']}")
    print(f"总轮数: {data['round_count']}")
    
    # ========== 阶段4: 用户画像总结 ==========
    print("\n【阶段4】用户画像总结")
    print("-" * 70)
    
    # 获取最后一次评估的用户画像
    response = requests.post(
        f"{BASE_URL}/conversations/{conversation_id}/respond",
        json={"user_response": "Thank you for the conversation!"}
    )
    data = response.json()
    user_profile = data['user_profile']
    
    print(f"最终综合分数: {user_profile['overall_score']:.1f}/100")
    print(f"最终CEFR等级: {user_profile['cefr_level']}")
    print(f"总对话轮数: {user_profile['conversation_count']}")
    print(f"强项: {', '.join(user_profile['strengths']) if user_profile['strengths'] else '无'}")
    print(f"弱项: {', '.join(user_profile['weaknesses']) if user_profile['weaknesses'] else '无'}")
    
    print("\n" + "=" * 70)
    print(" Demo完成！")
    print("=" * 70)

if __name__ == "__main__":
    try:
        demo_full_workflow()
    except Exception as e:
        print(f"\n❌ Demo失败: {e}")
        import traceback
        traceback.print_exc()
```

## 三、运行Demo

### 3.1 运行基础文本Demo

```bash
# 确保服务已启动
# 在另一个终端运行
python demo_text.py
```

### 3.2 运行语音Demo

```bash
# 准备音频文件（mp3, wav等格式）
python demo_speech.py your_audio_file.mp3
```

### 3.3 运行完整流程Demo

```bash
python demo_full.py
```

## 四、使用测试客户端

```bash
# 交互式测试
python test_client.py
```

## 五、使用curl测试

### 5.1 开始对话

```bash
curl -X POST "http://localhost:8000/conversations/start" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user"}'
```

### 5.2 回答问题（中英文混杂）

```bash
curl -X POST "http://localhost:8000/conversations/{conversation_id}/respond" \
  -H "Content-Type: application/json" \
  -d '{"user_response": "I am a student. 我喜欢读书。"}'
```

### 5.3 语音输入（如果已启用）

```bash
curl -X POST "http://localhost:8000/conversations/{conversation_id}/respond-audio" \
  -F "audio_file=@your_audio.mp3"
```

## 六、预期输出示例

### 文本对话输出

```
============================================================
 Demo: 文本对话流程
============================================================

1️⃣ 开始对话...
✅ 对话已开始
   对话ID: abc123-def456-ghi789
   初始问题: Can you tell me about yourself?

1️⃣ 第1轮回答
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

## 七、测试检查清单

- [ ] 服务启动成功
- [ ] 可以开始对话
- [ ] 可以回答问题
- [ ] 评估功能正常
- [ ] 中英文混杂处理正常
- [ ] 用户画像更新正常
- [ ] 难度自适应调整正常
- [ ] 题目生成正常
- [ ] 多轮对话连贯性正常

## 八、故障排查

### 问题1: 服务未启动
```bash
# 检查服务是否运行
curl http://localhost:8000/
```

### 问题2: API密钥错误
```bash
# 检查配置
python scripts/check_config.py
```

### 问题3: 导入错误
```bash
# 确保在项目根目录
cd /home/ubuntu/learning_english
# 安装依赖
pip install -r requirements.txt
```

