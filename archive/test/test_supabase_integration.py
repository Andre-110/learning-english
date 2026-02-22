#!/usr/bin/env python3
"""
测试 Supabase 数据库集成
"""
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.repository import RepositoryFactory
from models.conversation import Conversation, MessageRole, ConversationState
from models.user import UserProfile, CEFRLevel

def test_supabase_repositories():
    """测试 Supabase 存储实现"""
    print("=" * 60)
    print("测试 Supabase 数据库集成")
    print("=" * 60)
    
    # 创建 Supabase 存储实例
    try:
        conversation_repo, user_repo = RepositoryFactory.create_repositories(backend="supabase")
        print("\n✅ 成功创建 Supabase 存储实例")
    except Exception as e:
        print(f"\n❌ 创建存储实例失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试用户存储
    print("\n1. 测试用户存储...")
    test_user_id = "test_user_001"
    
    try:
        # 创建或获取用户
        user_profile = user_repo.get_or_create(test_user_id)
        print(f"  ✅ 创建/获取用户: {user_profile.user_id}")
        print(f"     初始分数: {user_profile.overall_score}, CEFR: {user_profile.cefr_level.value}")
        
        # 更新用户画像
        user_profile.overall_score = 65.5
        user_profile.cefr_level = CEFRLevel.B1
        user_profile.strengths = ["内容相关性", "语言准确性"]
        user_profile.weaknesses = ["交互深度", "词汇丰富度"]
        user_profile.conversation_count = 1
        
        user_repo.save(user_profile)
        print(f"  ✅ 保存用户画像")
        
        # 读取用户画像
        saved_user = user_repo.get(test_user_id)
        if saved_user:
            print(f"  ✅ 读取用户画像: 分数={saved_user.overall_score}, CEFR={saved_user.cefr_level.value}")
            print(f"     强项: {saved_user.strengths}")
            print(f"     弱项: {saved_user.weaknesses}")
        else:
            print(f"  ❌ 读取用户画像失败")
            return False
            
    except Exception as e:
        print(f"  ❌ 用户存储测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试对话存储
    print("\n2. 测试对话存储...")
    test_conv_id = f"test_conv_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    try:
        # 创建对话
        conversation = Conversation(
            conversation_id=test_conv_id,
            user_id=test_user_id,
            state=ConversationState.IN_PROGRESS
        )
        
        # 添加消息
        conversation.add_message(MessageRole.ASSISTANT, "Hello! How are you today?")
        conversation.add_message(MessageRole.USER, "I'm fine, thank you!")
        conversation.add_message(MessageRole.ASSISTANT, "That's great! What would you like to talk about?")
        
        conversation_repo.save(conversation)
        print(f"  ✅ 保存对话: {test_conv_id}")
        print(f"     消息数: {len(conversation.messages)}")
        
        # 读取对话
        saved_conv = conversation_repo.get(test_conv_id)
        if saved_conv:
            print(f"  ✅ 读取对话: {saved_conv.conversation_id}")
            print(f"     状态: {saved_conv.state.value}")
            print(f"     消息数: {len(saved_conv.messages)}")
            for idx, msg in enumerate(saved_conv.messages[:3], 1):
                print(f"     消息{idx}: [{msg.role.value}] {msg.content[:50]}...")
        else:
            print(f"  ❌ 读取对话失败")
            return False
        
        # 更新对话
        conversation.state = ConversationState.COMPLETED
        conversation.summary = "测试对话摘要"
        conversation.summary_round = 1
        conversation.add_message(MessageRole.USER, "I want to learn English.")
        
        conversation_repo.save(conversation)
        print(f"  ✅ 更新对话")
        
        # 再次读取验证更新
        updated_conv = conversation_repo.get(test_conv_id)
        if updated_conv and updated_conv.state == ConversationState.COMPLETED:
            print(f"  ✅ 验证更新: 状态={updated_conv.state.value}, 摘要={updated_conv.summary[:30]}...")
        else:
            print(f"  ❌ 验证更新失败")
            return False
        
        # 测试获取用户的所有对话
        user_convs = conversation_repo.get_by_user(test_user_id)
        print(f"  ✅ 获取用户对话列表: {len(user_convs)} 个对话")
        
    except Exception as e:
        print(f"  ❌ 对话存储测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = test_supabase_repositories()
    sys.exit(0 if success else 1)

