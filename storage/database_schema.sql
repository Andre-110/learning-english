-- 英语学习对话评估系统数据库表结构设计
-- 数据库: PostgreSQL (推荐) 或 MySQL

-- ============================================
-- 1. 用户表 (users)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 用户画像
    overall_score DECIMAL(5,2) DEFAULT 0.0 COMMENT '综合分数 0-100',
    cefr_level VARCHAR(10) DEFAULT 'A1' COMMENT 'CEFR等级: A1, A2, B1, B2, C1, C2',
    conversation_count INT DEFAULT 0 COMMENT '总对话轮数',
    
    -- 强项和弱项（JSON格式存储）
    strengths JSON COMMENT '强项列表，如 ["词汇丰富", "表达流畅"]',
    weaknesses JSON COMMENT '弱项列表，如 ["语法准确性", "复杂句式"]',
    
    -- 元数据
    metadata JSON COMMENT '额外的用户元数据',
    
    INDEX idx_cefr_level (cefr_level),
    INDEX idx_overall_score (overall_score),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ============================================
-- 2. 对话表 (conversations)
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL COMMENT '对话完成时间',
    
    -- 对话状态
    state VARCHAR(20) DEFAULT 'INITIALIZING' COMMENT '状态: INITIALIZING, IN_PROGRESS, COMPLETED, CANCELLED',
    
    -- 上下文管理
    summary TEXT COMMENT '对话摘要',
    summary_round INT DEFAULT 0 COMMENT '摘要对应的轮数',
    
    -- 元数据
    metadata JSON COMMENT '对话元数据',
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_state (state),
    INDEX idx_created_at (created_at),
    INDEX idx_completed_at (completed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话表';

-- ============================================
-- 3. 消息表 (messages)
-- ============================================
CREATE TABLE IF NOT EXISTS messages (
    message_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    
    -- 消息内容
    role VARCHAR(20) NOT NULL COMMENT '角色: system, user, assistant',
    content TEXT NOT NULL COMMENT '消息内容',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 元数据（JSON格式，包含评估结果等）
    metadata JSON COMMENT '消息元数据，如评估结果、转录信息等',
    
    -- 排序字段
    sequence_number INT NOT NULL COMMENT '消息在对话中的序号',
    
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_role (role),
    INDEX idx_created_at (created_at),
    INDEX idx_sequence_number (conversation_id, sequence_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息表';

-- ============================================
-- 4. 评估结果表 (assessments)
-- ============================================
CREATE TABLE IF NOT EXISTS assessments (
    assessment_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    
    -- 评估基本信息
    round_number INT NOT NULL COMMENT '评估轮次',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 能力画像
    overall_score DECIMAL(5,2) NOT NULL COMMENT '综合分数 0-100',
    cefr_level VARCHAR(10) NOT NULL COMMENT 'CEFR等级',
    confidence DECIMAL(3,2) DEFAULT 0.5 COMMENT '评估置信度 0-1',
    
    -- 强项和弱项
    strengths JSON COMMENT '强项列表',
    weaknesses JSON COMMENT '弱项列表',
    
    -- 维度评分（JSON格式存储）
    dimension_scores JSON NOT NULL COMMENT '维度评分列表，包含dimension, score, comment, reasoning',
    
    -- 原始响应
    raw_response JSON COMMENT 'LLM原始响应',
    
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_user_id (user_id),
    INDEX idx_round_number (conversation_id, round_number),
    INDEX idx_timestamp (timestamp),
    INDEX idx_overall_score (overall_score),
    INDEX idx_cefr_level (cefr_level),
    UNIQUE KEY uk_conversation_round (conversation_id, round_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='评估结果表';

-- ============================================
-- 5. 学习报告表 (learning_reports)
-- ============================================
CREATE TABLE IF NOT EXISTS learning_reports (
    report_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    
    -- 报告内容
    report_content TEXT NOT NULL COMMENT '报告内容（Markdown格式）',
    report_type VARCHAR(50) DEFAULT 'final' COMMENT '报告类型: final, progress, custom',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 元数据
    metadata JSON COMMENT '报告元数据',
    
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at),
    INDEX idx_report_type (report_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学习报告表';

-- ============================================
-- 6. 音频文件表 (audio_files) - 可选
-- ============================================
CREATE TABLE IF NOT EXISTS audio_files (
    audio_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    message_id BIGINT COMMENT '关联的消息ID',
    
    -- 文件信息
    file_path VARCHAR(500) NOT NULL COMMENT '文件存储路径',
    file_size BIGINT COMMENT '文件大小（字节）',
    file_type VARCHAR(50) COMMENT '文件类型: mp3, wav, m4a等',
    duration DECIMAL(10,2) COMMENT '音频时长（秒）',
    
    -- 转录信息
    transcribed_text TEXT COMMENT '转录文本',
    transcription_provider VARCHAR(50) COMMENT '转录服务提供商: whisper, funasr',
    transcription_confidence DECIMAL(3,2) COMMENT '转录置信度',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE SET NULL,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_message_id (message_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='音频文件表';

-- ============================================
-- 7. 用户学习进度表 (user_progress) - 可选
-- ============================================
CREATE TABLE IF NOT EXISTS user_progress (
    progress_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    
    -- 进度信息
    date DATE NOT NULL COMMENT '日期',
    conversation_count INT DEFAULT 0 COMMENT '当日对话轮数',
    total_score DECIMAL(5,2) COMMENT '当日平均分数',
    
    -- 学习时长
    study_duration_minutes INT DEFAULT 0 COMMENT '学习时长（分钟）',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_date (date),
    UNIQUE KEY uk_user_date (user_id, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户学习进度表';

-- ============================================
-- 视图：用户对话统计视图
-- ============================================
CREATE OR REPLACE VIEW user_conversation_stats AS
SELECT 
    u.user_id,
    u.overall_score,
    u.cefr_level,
    u.conversation_count,
    COUNT(DISTINCT c.conversation_id) as total_conversations,
    MAX(c.created_at) as last_conversation_at,
    AVG(a.overall_score) as avg_assessment_score
FROM users u
LEFT JOIN conversations c ON u.user_id = c.user_id
LEFT JOIN assessments a ON c.conversation_id = a.conversation_id
GROUP BY u.user_id, u.overall_score, u.cefr_level, u.conversation_count;

-- ============================================
-- 视图：对话详情视图（包含消息和评估）
-- ============================================
CREATE OR REPLACE VIEW conversation_details AS
SELECT 
    c.conversation_id,
    c.user_id,
    c.state,
    c.created_at,
    c.completed_at,
    COUNT(DISTINCT m.message_id) as message_count,
    COUNT(DISTINCT a.assessment_id) as assessment_count,
    MAX(a.overall_score) as max_score,
    MIN(a.overall_score) as min_score,
    AVG(a.overall_score) as avg_score
FROM conversations c
LEFT JOIN messages m ON c.conversation_id = m.conversation_id
LEFT JOIN assessments a ON c.conversation_id = a.conversation_id
GROUP BY c.conversation_id, c.user_id, c.state, c.created_at, c.completed_at;

