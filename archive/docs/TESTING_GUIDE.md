# 测试指南

## 重要提示：清除浏览器缓存

**在测试之前，请务必清除浏览器缓存！**

### Chrome/Edge:
1. 按 `Ctrl+Shift+Delete` (Windows) 或 `Cmd+Shift+Delete` (Mac)
2. 选择"缓存的图片和文件"
3. 点击"清除数据"
4. 或者按 `Ctrl+F5` 强制刷新页面

### Firefox:
1. 按 `Ctrl+Shift+Delete`
2. 选择"缓存"
3. 点击"立即清除"
4. 或者按 `Ctrl+F5` 强制刷新

---

## 功能测试步骤

### 1. 测试系统回答用户问题

**测试步骤：**
1. 打开浏览器，访问 `http://localhost:8000/`
2. **清除浏览器缓存**（重要！）
3. 输入用户ID（如 `user_001`）
4. 点击"开始对话"
5. 点击"开始录音"
6. 说："你是谁" 或 "who are you"
7. 点击"停止录音"

**预期结果：**
- 系统应该先回答："I'm LinguaCoach, your English learning assistant..."
- 然后继续问新的学习问题

**如果仍然不工作：**
- 打开浏览器开发者工具（F12）
- 查看 Console 标签页
- 查看是否有错误信息
- 查看 Network 标签页，确认 WebSocket 连接正常

---

### 2. 测试用户画像和评估更新

**测试步骤：**
1. 完成一次完整的对话（录音 → 停止 → 等待处理）
2. 查看右侧面板的"用户画像"和"最新评估"部分

**预期结果：**
- "用户画像"应该显示：
  - 用户ID
  - 综合分数（如 65.0/100）
  - CEFR等级（如 A1）
  - 对话轮数
- "最新评估"应该显示：
  - 综合分数
  - CEFR等级
  - 强项列表
  - 弱项列表

**如果仍然不显示：**
1. 打开浏览器开发者工具（F12）
2. 查看 Console 标签页
3. 应该看到类似这样的日志：
   ```
   收到评估数据: {...}
   更新评估显示，分数: 65.0 等级: A1
   更新用户画像: {...}
   ```
4. 如果看到错误，请记录错误信息

---

### 3. 测试性能测试功能

**测试步骤：**
1. 点击"🚀 开始性能测试"按钮
2. 点击"开始录音"
3. 说几句话
4. 点击"停止录音"
5. 等待处理完成

**预期结果：**
- 性能测试区域应该显示各个阶段的耗时：
  - 录音时间
  - 音频发送
  - 首次转录
  - 最终转录
  - 评估处理
  - 问题生成
  - TTS生成
  - 总处理时间
- 每个指标应该有颜色标识（绿色=快速，黄色=中等，红色=缓慢）

---

## 调试信息

### 后端日志
查看服务日志：
```bash
tail -f /tmp/uvicorn.log
```

关键日志信息：
- `[process_user_response] User is asking a question:` - 检测到用户问题
- `[process_user_response] Generated answer:` - 生成回答
- `[process_audio_input] 发送评估数据:` - 发送评估数据

### 前端日志
打开浏览器开发者工具（F12），查看 Console：
- `收到评估数据:` - 收到评估消息
- `更新评估显示` - 更新UI
- `更新用户画像` - 更新用户画像

---

## 常见问题

### Q: 系统仍然不回答我的问题
**A:** 
1. 确保已清除浏览器缓存
2. 检查浏览器控制台是否有错误
3. 确认服务已重启（检查 `/tmp/uvicorn.log`）
4. 测试问题检测：说 "你是谁" 或 "who are you"

### Q: 用户画像和评估不显示
**A:**
1. 打开浏览器控制台，查看是否有 `收到评估数据` 日志
2. 如果没有日志，可能是 WebSocket 连接问题
3. 如果有日志但UI不更新，检查 `updateAssessment` 函数是否被调用
4. 检查评估数据格式是否正确

### Q: 性能测试不显示数据
**A:**
1. 确保先点击"开始性能测试"按钮
2. 然后进行录音
3. 完成一次完整的对话流程
4. 检查浏览器控制台是否有性能相关的日志

---

## 验证代码是否正确部署

### 检查问题检测逻辑：
```bash
cd /home/ubuntu/learning_english
source venv/bin/activate
python3 -c "
from core.conversation import ConversationManager
from api.main import get_conversation_manager
manager = get_conversation_manager()
print('你是谁:', manager._is_user_asking_question('你是谁'))
print('who are you:', manager._is_user_asking_question('who are you'))
"
```

应该输出：
```
你是谁: True
who are you: True
```

### 检查服务是否运行：
```bash
curl http://localhost:8000/api
```

应该返回：
```json
{"message":"LinguaCoach API","version":"1.0.0","status":"running"}
```

---

## 如果问题仍然存在

1. **重启服务：**
   ```bash
   pkill -f "uvicorn api.main:app"
   cd /home/ubuntu/learning_english
   source venv/bin/activate
   python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```

2. **清除浏览器缓存并强制刷新**

3. **检查日志：**
   - 后端：`tail -f /tmp/uvicorn.log`
   - 前端：浏览器开发者工具 Console

4. **提供调试信息：**
   - 浏览器控制台的错误信息
   - 后端日志中的错误信息
   - 具体的操作步骤和预期结果

