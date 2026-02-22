# 语音风格预览音频

此目录存放语音风格的预览 demo 音频文件。

## 文件列表

- `voice-preview-friendly.mp3` - 友好导师
- `voice-preview-professional.mp3` - 专业教师
- `voice-preview-energetic.mp3` - 活力教练
- `voice-preview-calm.mp3` - 沉稳向导
- `voice-preview-storyteller.mp3` - 故事讲述者
- `voice-preview-natural.mp3` - 自然对话

## 生成方式

运行以下命令生成预览音频：

```bash
cd /home/ubuntu/learning_english
python scripts/generate_voice_previews.py
```

需要：
1. 正确配置 OpenAI API Key
2. 安装 ffmpeg（用于 PCM 转 MP3）

