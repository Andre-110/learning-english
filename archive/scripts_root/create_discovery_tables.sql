-- 每日发现模块数据表
-- 在 Supabase Dashboard 的 SQL Editor 中执行

-- 1. 文章表：存储生成的文章
CREATE TABLE IF NOT EXISTS discovery_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    topic VARCHAR(50),                    -- 预设话题ID (tech, health, etc.)
    custom_topic TEXT,                    -- 自定义话题文本
    cefr_level VARCHAR(10) DEFAULT 'B1',
    simplified_content JSONB,             -- 简化版内容 (数组)
    original_content JSONB,               -- 原版内容 (数组)
    vocabulary JSONB,                     -- 词汇列表
    quiz JSONB,                           -- 测验题目
    grammar_focus JSONB,                  -- 语法重点
    source TEXT,                          -- 原文来源
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 交互记录表：存储用户与文章的交互
CREATE TABLE IF NOT EXISTS discovery_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    article_id UUID NOT NULL REFERENCES discovery_articles(id) ON DELETE CASCADE,
    interaction_type VARCHAR(50) NOT NULL,  -- 'chat', 'quiz', 'voice_chat', 'reading'
    content JSONB NOT NULL,                 -- 交互内容 (用户消息、AI回复、测验结果等)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 用户生词本
CREATE TABLE IF NOT EXISTS user_vocabulary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    word VARCHAR(100) NOT NULL,
    phonetic VARCHAR(100),                  -- 音标
    definition TEXT,                        -- 释义（中英双语）
    example_sentence TEXT,                  -- 例句
    source_article_id UUID REFERENCES discovery_articles(id) ON DELETE SET NULL,
    mastery_level INTEGER DEFAULT 0,        -- 0: 新词, 1: 认识, 2: 熟悉, 3: 掌握
    review_count INTEGER DEFAULT 0,         -- 复习次数
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_reviewed_at TIMESTAMPTZ,
    
    -- 同一用户的同一单词只能有一条记录
    UNIQUE(user_id, word)
);

-- 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_discovery_articles_user_id ON discovery_articles(user_id);
CREATE INDEX IF NOT EXISTS idx_discovery_articles_created_at ON discovery_articles(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_discovery_interactions_article_id ON discovery_interactions(article_id);
CREATE INDEX IF NOT EXISTS idx_discovery_interactions_user_id ON discovery_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_vocabulary_user_id ON user_vocabulary(user_id);
CREATE INDEX IF NOT EXISTS idx_user_vocabulary_mastery ON user_vocabulary(user_id, mastery_level);

-- 启用 RLS (Row Level Security)
ALTER TABLE discovery_articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE discovery_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_vocabulary ENABLE ROW LEVEL SECURITY;

-- RLS 策略：允许所有操作（简化版，生产环境应该更严格）
-- 删除已存在的策略（如果有）
DROP POLICY IF EXISTS "Allow all on discovery_articles" ON discovery_articles;
DROP POLICY IF EXISTS "Allow all on discovery_interactions" ON discovery_interactions;
DROP POLICY IF EXISTS "Allow all on user_vocabulary" ON user_vocabulary;

-- 创建新策略
CREATE POLICY "Allow all on discovery_articles" ON discovery_articles FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on discovery_interactions" ON discovery_interactions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on user_vocabulary" ON user_vocabulary FOR ALL USING (true) WITH CHECK (true);
