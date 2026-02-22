#!/usr/bin/env python3
"""
生成语音风格预览音频

运行方式：
    cd /home/ubuntu/learning_english
    python scripts/generate_voice_previews.py

生成的文件会保存到 frontend/public/audio/ 目录
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.voice_styles import VOICE_STYLES
from services.gpt4o_pipeline import create_gpt4o_pipeline

# 预览文本（每种风格使用不同的示例，展示风格特点）
PREVIEW_TEXTS = {
    "friendly": "Hey there! Great job practicing today. Keep up the amazing work, you're doing fantastic!",
    "professional": "Let's review the grammar structure. Notice how the verb agrees with the subject in this sentence.",
    "energetic": "Wow, that was incredible! You're making such great progress! Let's keep this momentum going!",
    "calm": "Take your time. There's no rush. Let's go through this together, nice and easy.",
    "storyteller": "Picture this... You're walking through a bustling market in London, and suddenly you hear someone call your name.",
    "natural": "So, I was thinking... maybe we could talk about what you did over the weekend? Anything interesting?",
}

def generate_previews():
    """生成所有风格的预览音频"""
    
    # 输出目录
    output_dir = project_root / "frontend" / "public" / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"输出目录: {output_dir}")
    print("-" * 50)
    
    # 创建 pipeline
    pipeline = create_gpt4o_pipeline()
    
    for style_id, style in VOICE_STYLES.items():
        text = PREVIEW_TEXTS.get(style_id, "Hello! I'm your English learning assistant.")
        
        print(f"\n生成 [{style.name_zh}] ({style_id})...")
        print(f"  文本: {text[:50]}...")
        print(f"  语音: {style.voice}, 语速: {style.speed}")
        
        try:
            # 生成 PCM 音频
            pcm_data = pipeline.synthesize(
                text=text,
                voice=style.voice,
                speed=style.speed,
                instructions=style.instructions,
                stream=False
            )
            
            # 保存为 PCM 文件（原始格式）
            pcm_path = output_dir / f"voice-preview-{style_id}.pcm"
            with open(pcm_path, "wb") as f:
                f.write(pcm_data)
            
            print(f"  ✅ PCM 已保存: {pcm_path.name} ({len(pcm_data)} bytes)")
            
            # 转换为 MP3（需要 ffmpeg）
            mp3_path = output_dir / f"voice-preview-{style_id}.mp3"
            
            import subprocess
            result = subprocess.run([
                "ffmpeg", "-y",
                "-f", "s16le",      # 输入格式：16-bit signed little-endian
                "-ar", "24000",     # 采样率
                "-ac", "1",         # 单声道
                "-i", str(pcm_path),
                "-codec:a", "libmp3lame",
                "-b:a", "128k",
                str(mp3_path)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"  ✅ MP3 已保存: {mp3_path.name}")
                # 删除 PCM 文件
                pcm_path.unlink()
            else:
                print(f"  ⚠️ MP3 转换失败: {result.stderr[:100]}")
                print(f"  保留 PCM 文件: {pcm_path.name}")
            
        except Exception as e:
            print(f"  ❌ 生成失败: {e}")
    
    print("\n" + "=" * 50)
    print("✅ 完成！")
    print(f"文件位置: {output_dir}")


if __name__ == "__main__":
    generate_previews()

