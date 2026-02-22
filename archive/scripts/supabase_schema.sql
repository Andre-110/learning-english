-- Supabase 数据库表结构
-- 在 Supabase Dashboard > SQL Editor 中执行此脚本

-- 1. 用户表 (users)
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- 能力画像字段
    overall_score REAL DEFAULT 0.0,
    cefr_level VARCHAR(10) DEFAULT 'A1',
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    conversation_count INT DEFAULT 0,
    
    -- 其他元数据
    metadata JSONB DEFAULT '{}'
);

-- 2. 对话会话表 (conversations)
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    state VARCHAR(50) DEFAULT 'IN_PROGRESS',
    current_round INT DEFAULT 0,
    summary TEXT,
    summary_round INT DEFAULT 0,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- 3. 对话消息表 (messages)
CREATE TABLE IF NOT EXISTS messages (
    message_id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    round_number INT NOT NULL,
    sender_role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
);

-- 4. 评估结果表 (assessments)
CREATE TABLE IF NOT EXISTS assessments (
    assessment_id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    round_number INT NOT NULL,
    overall_score REAL NOT NULL,
    cefr_level VARCHAR(10) NOT NULL,
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    dimension_scores JSONB DEFAULT '[]',
    raw_llm_response JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- 5. 学习报告表 (learning_reports)
CREATE TABLE IF NOT EXISTS learning_reports (
    report_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    conversation_id VARCHAR(255),
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    report_content TEXT NOT NULL,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE SET NULL
);

-- 6. 音频文件表 (audio_files)
CREATE TABLE IF NOT EXISTS audio_files (
    audio_id SERIAL PRIMARY KEY,
    message_id INT UNIQUE,
    file_path VARCHAR(512) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    
    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE SET NULL
);

-- 7. 用户学习进度表 (user_progress)
CREATE TABLE IF NOT EXISTS user_progress (
    progress_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    skill_area VARCHAR(255),
    topic_area VARCHAR(255),
    latest_score REAL,
    latest_cefr_level VARCHAR(10),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (user_id, skill_area, topic_area)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_cefr_level ON users (cefr_level);
CREATE INDEX IF NOT EXISTS idx_users_overall_score ON users (overall_score);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_state ON conversations (state);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_round_number ON messages (conversation_id, round_number);
CREATE INDEX IF NOT EXISTS idx_assessments_conversation_id ON assessments (conversation_id);
CREATE INDEX IF NOT EXISTS idx_assessments_user_id ON assessments (user_id);
CREATE INDEX IF NOT EXISTS idx_assessments_round_number ON assessments (conversation_id, round_number);
CREATE INDEX IF NOT EXISTS idx_learning_reports_user_id ON learning_reports (user_id);
CREATE INDEX IF NOT EXISTS idx_audio_files_message_id ON audio_files (message_id);
CREATE INDEX IF NOT EXISTS idx_user_progress_user_id ON user_progress (user_id);

