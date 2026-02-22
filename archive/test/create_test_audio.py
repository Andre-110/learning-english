#!/usr/bin/env python3
"""
创建测试音频文件 - 使用文本转语音
"""
import sys
import os

def create_audio_with_gtts():
    """使用gTTS创建测试音频"""
    try:
        from gtts import gTTS
        print("✅ gTTS已安装")
    except ImportError:
        print("❌ gTTS未安装")
        print("   安装命令: pip install gtts")
        return False
    
    # 创建输出目录
    audio_dir = "test_audio"
    os.makedirs(audio_dir, exist_ok=True)
    
    print(f"\n创建测试音频文件到: {audio_dir}/")
    print("-" * 70)
    
    # 测试用例
    test_cases = [
        {
            "filename": "test_simple.mp3",
            "text": "I am a student. I like reading books.",
            "level": "A1-A2",
            "description": "简单句子"
        },
        {
            "filename": "test_medium.mp3",
            "text": "I am a student. I like reading books very much. Reading helps me learn new words and improve my English skills. I read for about 30 minutes every day.",
            "level": "B1",
            "description": "中等难度"
        },
        {
            "filename": "test_advanced.mp3",
            "text": "As an avid reader, I find that immersing myself in literature not only expands my vocabulary but also enhances my linguistic proficiency. The intricate narratives and sophisticated language structures provide invaluable insights into effective communication.",
            "level": "B2-C1",
            "description": "高级难度"
        },
        {
            "filename": "test_mixed.mp3",
            "text": "I am a student. 我喜欢读书。Reading helps me learn new words.",
            "level": "Mixed",
            "description": "中英文混合"
        }
    ]
    
    for case in test_cases:
        try:
            print(f"\n生成: {case['filename']} ({case['level']} - {case['description']})")
            tts = gTTS(text=case['text'], lang='en', slow=False)
            filepath = os.path.join(audio_dir, case['filename'])
            tts.save(filepath)
            
            # 检查文件大小
            size = os.path.getsize(filepath)
            print(f"   ✅ 成功 ({size/1024:.1f} KB)")
            
        except Exception as e:
            print(f"   ❌ 失败: {e}")
    
    print("\n" + "=" * 70)
    print("✅ 测试音频创建完成！")
    print(f"   位置: {audio_dir}/")
    print("\n使用方法:")
    print(f"  python test/test_listening.py")
    print("=" * 70)
    
    return True

def create_audio_with_say():
    """使用系统say命令创建音频（macOS）"""
    import subprocess
    
    audio_dir = "test_audio"
    os.makedirs(audio_dir, exist_ok=True)
    
    print("\n尝试使用系统say命令（macOS）...")
    
    test_texts = [
        ("test_simple.aiff", "I am a student. I like reading books."),
        ("test_medium.aiff", "I am a student. I like reading books very much. Reading helps me learn new words."),
    ]
    
    for filename, text in test_texts:
        try:
            filepath = os.path.join(audio_dir, filename)
            subprocess.run(["say", "-o", filepath, text], check=True)
            print(f"   ✅ 生成: {filename}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"   ⚠️  say命令不可用（仅macOS）")
            return False
    
    return True

if __name__ == "__main__":
    print("=" * 70)
    print("创建测试音频文件")
    print("=" * 70)
    
    # 优先使用gTTS
    if create_audio_with_gtts():
        exit(0)
    
    # 备选：使用say命令（macOS）
    if sys.platform == "darwin":
        if create_audio_with_say():
            exit(0)
    
    print("\n❌ 无法创建测试音频")
    print("\n请选择以下方法之一:")
    print("1. 安装gTTS: pip install gtts")
    print("2. 使用在线TTS工具生成音频")
    print("3. 使用手机录音功能")
    print("4. 从公开数据集下载测试音频")
    
    exit(1)





