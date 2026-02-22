# 测试音频文件来源

## 📚 推荐的测试音频资源

### 1. LibriVox（推荐）

**网站**: https://librivox.org/

**特点**:
- ✅ 完全免费，公有领域
- ✅ 大量英语有声读物
- ✅ 多种难度级别
- ✅ 高质量录音

**使用方法**:
1. 访问 https://librivox.org/
2. 搜索英语书籍
3. 下载MP3文件
4. 截取30-60秒片段用于测试

### 2. Common Voice（Mozilla）

**网站**: https://commonvoice.mozilla.org/

**特点**:
- ✅ 开源数据集
- ✅ 多种语言和方言
- ✅ 短句子音频（适合测试）
- ✅ 免费下载

**使用方法**:
1. 访问 https://commonvoice.mozilla.org/
2. 下载英语数据集
3. 使用其中的测试音频

### 3. 使用文本转语音（TTS）生成

**工具**: gTTS (Google Text-to-Speech)

**安装**:
```bash
pip install gtts
```

**使用方法**:
```python
from gtts import gTTS

tts = gTTS('I am a student. I like reading books.', lang='en')
tts.save('test_audio.mp3')
```

**脚本**: `test/create_test_audio.py`

### 4. 在线TTS工具

- **Google Translate**: https://translate.google.com/
  - 输入文本，点击语音按钮，录制音频

- **Natural Reader**: https://www.naturalreaders.com/
  - 在线文本转语音

- **TTSMaker**: https://ttsmaker.com/
  - 免费在线TTS工具

### 5. 使用系统录音

**Linux**:
```bash
# 使用arecord
arecord -d 5 -f cd test_audio.wav

# 使用sox
sox -d test_audio.wav
```

**macOS**:
```bash
# 使用say命令
say "I am a student. I like reading books." -o test_audio.aiff
```

**Windows**:
- 使用内置录音机应用
- 或使用Audacity等工具

## 🎯 测试音频要求

### 格式要求
- **推荐**: MP3, WAV
- **支持**: MP3, WAV, M4A, MP4, WEBM, MPEG, MPGA

### 内容要求
- **语言**: 英语或中英文混合
- **时长**: 5-30秒（推荐）
- **内容**: 回答问题的语音
- **质量**: 清晰，无明显噪音

### 测试用例建议

#### A1-A2级别
```
"I am a student. I like reading books."
"What is your name? My name is John."
"I go to school every day."
```

#### B1级别
```
"I am a student. I like reading books very much. Reading helps me learn new words and improve my English skills. I read for about 30 minutes every day."
```

#### B2-C1级别
```
"As an avid reader, I find that immersing myself in literature not only expands my vocabulary but also enhances my linguistic proficiency. The intricate narratives and sophisticated language structures provide invaluable insights into effective communication."
```

## 🛠️ 快速创建测试音频

### 方法1: 使用我们的脚本

```bash
# 安装gTTS
pip install gtts

# 运行脚本
python test/create_test_audio.py
```

### 方法2: 手动创建

```python
from gtts import gTTS

# 创建简单测试音频
tts = gTTS('I am a student. I like reading books.', lang='en')
tts.save('test_audio.mp3')
```

### 方法3: 从LibriVox下载

1. 访问 https://librivox.org/
2. 选择一个短篇故事或章节
3. 下载MP3文件
4. 使用音频编辑工具截取片段

## 📝 测试音频文件位置

创建或下载的测试音频文件应放在：
- `test_audio/` 目录（推荐）
- 或项目根目录

测试脚本会自动查找这些位置的音频文件。

## 🔍 验证音频文件

```bash
# 检查音频文件
ls -lh test_audio/*.mp3

# 播放音频（如果系统支持）
# Linux: mpg123 test_audio/test_simple.mp3
# macOS: afplay test_audio/test_simple.mp3
```

## 📋 测试音频清单

建议准备以下测试音频：

- [ ] `test_simple.mp3` - 简单句子（A1-A2）
- [ ] `test_medium.mp3` - 中等难度（B1）
- [ ] `test_advanced.mp3` - 高级难度（B2-C1）
- [ ] `test_mixed.mp3` - 中英文混合

## ⚠️ 注意事项

1. **版权**: 确保使用的音频文件符合版权要求
2. **质量**: 使用清晰的音频，避免背景噪音
3. **格式**: 确保音频格式被支持
4. **大小**: 建议单个文件不超过25MB（Whisper API限制）

## 🚀 快速开始

```bash
# 1. 安装gTTS
pip install gtts

# 2. 创建测试音频
python test/create_test_audio.py

# 3. 运行听力测试
python test/test_listening.py
```

## 📚 相关资源

- **LibriVox**: https://librivox.org/
- **Common Voice**: https://commonvoice.mozilla.org/
- **gTTS文档**: https://gtts.readthedocs.io/
- **Whisper API文档**: https://platform.openai.com/docs/guides/speech-to-text





