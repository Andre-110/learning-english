#!/usr/bin/env python3
"""
配置检查脚本 - 检查系统配置是否正确
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

print("=" * 60)
print("配置检查")
print("=" * 60)

# 检查LLM配置
print("\n1. LLM配置:")
llm_provider = os.getenv("LLM_PROVIDER", "openai")
print(f"   LLM Provider: {llm_provider}")

if llm_provider.lower() == "openai":
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_base_url = os.getenv("OPENAI_BASE_URL")
    primary_model = os.getenv("PRIMARY_LLM_MODEL", "gpt-4-turbo")
    
    print(f"   OpenAI API Key: {'已设置' if openai_key else '❌ 未设置'}")
    print(f"   OpenAI Base URL: {openai_base_url or '使用默认'}")
    print(f"   Primary Model: {primary_model}")
    
    if not openai_key:
        print("\n   ⚠️  警告: OPENAI_API_KEY 未设置！")
        print("   请在 .env 文件中设置 OPENAI_API_KEY")
        
elif llm_provider.lower() == "anthropic":
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    primary_model = os.getenv("PRIMARY_LLM_MODEL", "claude-3-opus-20240229")
    
    print(f"   Anthropic API Key: {'已设置' if anthropic_key else '❌ 未设置'}")
    print(f"   Primary Model: {primary_model}")
    
    if not anthropic_key:
        print("\n   ⚠️  警告: ANTHROPIC_API_KEY 未设置！")
        print("   请在 .env 文件中设置 ANTHROPIC_API_KEY")

# 检查存储配置
print("\n2. 存储配置:")
storage_backend = os.getenv("STORAGE_BACKEND", "memory")
print(f"   Storage Backend: {storage_backend}")

if storage_backend == "supabase":
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    print(f"   Supabase URL: {'已设置' if supabase_url else '❌ 未设置'}")
    print(f"   Supabase Key: {'已设置' if supabase_key else '❌ 未设置'}")

# 检查语音服务配置
print("\n3. 语音服务配置:")
speech_provider = os.getenv("SPEECH_PROVIDER", "whisper")
print(f"   Speech Provider: {speech_provider}")

tts_provider = os.getenv("TTS_PROVIDER", "openai")
print(f"   TTS Provider: {tts_provider}")

# 检查.env文件
print("\n4. 环境变量文件:")
env_file = ".env"
if os.path.exists(env_file):
    print(f"   ✓ .env 文件存在")
    with open(env_file, 'r') as f:
        lines = f.readlines()
        print(f"   包含 {len(lines)} 行配置")
else:
    print(f"   ⚠️  .env 文件不存在")
    print("   建议创建 .env 文件并设置必要的配置")

print("\n" + "=" * 60)
print("检查完成")
print("=" * 60)



