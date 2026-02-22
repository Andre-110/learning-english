# qwen-omni Prompt 遵循能力改进总结

## ✅ 已完成的改进

### 1. 优化 Prompt - 强调中文转录准确性 ⭐⭐⭐⭐⭐

**文件**: `prompts/templates.py`

**改进内容**:
1. **明确要求使用中文汉字而非拼音**:
   - 添加规则：`If they spoke CHINESE → write Chinese (中文汉字，NOT pinyin!)`
   - 强调：`DO NOT convert Chinese to pinyin! Write Chinese characters (汉字)!`

2. **添加拼音识别和修正指导**:
   - 如果听到类似拼音的声音（如 "zu qiu", "lan qiu"），应识别为中文词并写成汉字（足球, 篮球）
   - 提供示例：`If audio sounds like "tsuuchio" or "zu qiu" but context suggests it's "足球" → Transcribe: "足球"`

3. **增强中文处理指导**:
   - 在修正建议部分，明确要求：如果转录中包含拼音（如 "zu qiu", "lan qiu", "tsuuchio"），应识别为中文词并修正
   - 提供修正示例：`"zu qiu" → "足球" → "soccer"`

**预期效果**:
- 模型能识别拼音化的中文并修正回中文汉字
- 提高中文保留率（从25%提升到更高）

---

### 2. 添加冗余修正过滤 ⭐⭐⭐⭐⭐

**文件**: `services/unified_processor.py`

**改进内容**:
1. **在 JSON 解析路径中添加过滤**:
   - 检查每个修正的 `original` 和 `corrected` 是否相同
   - 如果相同，自动过滤掉（不添加到结果中）
   - 记录日志以便调试

2. **在正则提取路径中也添加过滤**:
   - 确保即使 JSON 解析失败，正则提取的修正也会被过滤

**代码逻辑**:
```python
filtered_corrections = []
for corr in corrections:
    if isinstance(corr, dict):
        original = corr.get("original", "").strip()
        corrected = corr.get("corrected", "").strip()
        # 如果 original 和 corrected 相同，跳过（冗余修正）
        if original.lower() != corrected.lower() or original != corrected:
            filtered_corrections.append(corr)
```

**预期效果**:
- 消除冗余修正（从15.8%降到0%）
- 提高建议质量

---

### 3. 优化测试脚本 ⭐⭐⭐⭐

**文件**: `test_qwen_omni_prompt_following.py`

**改进内容**:
1. **添加详细的转录质量分析**:
   - 检查中文是否保留
   - 检查中英文混杂是否保留
   - 识别中文转录错误

2. **添加建议质量分析**:
   - 检测冗余修正
   - 检测中文处理情况
   - 检测分数合理性

3. **改进 TTS 生成**:
   - 优先尝试 edge-tts（支持中文）
   - 回退到 OpenAI TTS（当前环境 edge-tts 不可用）

**预期效果**:
- 更详细的测试报告
- 更好的问题识别

---

## 📊 预期改进效果

### 改进前 vs 改进后（预期）

| 指标 | 改进前 | 改进后（预期） | 改进幅度 |
|------|--------|----------------|----------|
| **中文保留率** | 25% | 50-70% | +25-45% |
| **冗余修正率** | 15.8% | 0% | -15.8% |
| **中文处理率** | 25% | 50-70% | +25-45% |
| **拼音识别** | 0% | 50-70% | +50-70% |

---

## 🔍 改进验证

测试正在运行中，将验证：
1. ✅ Prompt 优化是否提高了中文转录准确性
2. ✅ 冗余修正过滤是否生效
3. ✅ 拼音识别和修正是否工作

---

## 📝 后续优化建议

如果测试结果显示改进效果不理想，可以考虑：

1. **进一步优化 Prompt**:
   - 添加更多中文处理的示例
   - 强调上下文理解的重要性

2. **使用支持中文的 TTS**:
   - 在生产环境中使用 edge-tts 或其他支持中文的 TTS
   - 或使用混合 TTS（中文部分用中文 TTS，英文部分用英文 TTS）

3. **后处理优化**:
   - 添加拼音到中文的映射表
   - 自动修正常见拼音错误

---

## 🎯 改进优先级

1. ✅ **已完成**: Prompt 优化（高优先级）
2. ✅ **已完成**: 冗余修正过滤（高优先级）
3. ⏳ **待验证**: 测试结果验证（中优先级）
4. 📋 **待定**: TTS 改进（中优先级，需要环境支持）


