-- 添加用户兴趣相关字段和表
-- 在 Supabase Dashboard > SQL Editor 中执行

-- 1. 在 users 表中添加兴趣字段
ALTER TABLE users ADD COLUMN IF NOT EXISTS interests JSONB DEFAULT '[]';
-- 格式: [{"category": "news", "tags": ["technology", "AI"], "weight": 0.8, "last_discussed": "2025-12-07"}, ...]

-- 2. 在 conversations 表中添加兴趣匹配字段
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS interest_match_score REAL DEFAULT 0.0;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS matched_interests JSONB DEFAULT '[]';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS discussed_topics JSONB DEFAULT '[]';

-- 3. 创建对话模板表（用于存储预定义的对话模板）
CREATE TABLE IF NOT EXISTS conversation_templates (
    template_id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL, -- news, tech, sports, travel, etc.
    topic_name VARCHAR(255) NOT NULL,
    cefr_level VARCHAR(10) NOT NULL, -- A1-C2
    template_content TEXT NOT NULL, -- 对话模板内容
    keywords JSONB DEFAULT '[]', -- 关键词列表
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. 创建索引
CREATE INDEX IF NOT EXISTS idx_conversation_templates_category ON conversation_templates (category);
CREATE INDEX IF NOT EXISTS idx_conversation_templates_cefr_level ON conversation_templates (cefr_level);
CREATE INDEX IF NOT EXISTS idx_conversation_templates_active ON conversation_templates (is_active);

-- 5. 插入对话模板数据（新闻类）
INSERT INTO conversation_templates (category, topic_name, cefr_level, template_content, keywords, description) VALUES
('news', 'Technology News', 'B1', 'Have you heard about the latest developments in artificial intelligence? What do you think about how AI is changing our daily lives?', '["AI", "technology", "innovation", "future"]', '讨论最新科技新闻和AI发展'),
('news', 'Environmental News', 'B1', 'What are your thoughts on climate change? Have you noticed any environmental changes in your area?', '["climate", "environment", "green", "sustainability"]', '讨论环境新闻和气候变化'),
('news', 'Health News', 'A2', 'Have you been following any health news recently? What do you think about the importance of exercise?', '["health", "exercise", "wellness", "fitness"]', '讨论健康新闻和生活方式'),
('news', 'Economic News', 'B2', 'What do you think about the current economic situation? How do you think it affects ordinary people?', '["economy", "finance", "market", "business"]', '讨论经济新闻和市场动态'),
('news', 'Education News', 'B1', 'What are your thoughts on online learning? Do you think it will replace traditional education?', '["education", "learning", "online", "school"]', '讨论教育新闻和学习方式'),

-- 科技类
('tech', 'Smartphones', 'A2', 'What smartphone do you use? What features do you like most about it?', '["smartphone", "mobile", "app", "device"]', '讨论智能手机和移动设备'),
('tech', 'Social Media', 'B1', 'How do you use social media? What are the pros and cons of social media platforms?', '["social media", "facebook", "instagram", "communication"]', '讨论社交媒体和网络交流'),
('tech', 'Gaming', 'A2', 'Do you play video games? What types of games do you enjoy?', '["gaming", "video games", "entertainment", "online"]', '讨论电子游戏和娱乐'),
('tech', 'Programming', 'B2', 'Are you interested in programming? What programming languages do you know or want to learn?', '["programming", "coding", "software", "development"]', '讨论编程和软件开发'),
('tech', 'Internet of Things', 'B2', 'What smart devices do you have at home? How do you think IoT will change our lives?', '["IoT", "smart home", "connected", "automation"]', '讨论物联网和智能家居'),

-- 体育类
('sports', 'Football', 'A2', 'Do you like football? Who is your favorite team or player?', '["football", "soccer", "team", "match"]', '讨论足球和比赛'),
('sports', 'Basketball', 'A2', 'Have you ever played basketball? What do you think makes it exciting?', '["basketball", "NBA", "sport", "athlete"]', '讨论篮球和运动'),
('sports', 'Olympics', 'B1', 'What is your favorite Olympic sport? What do you think about the Olympic spirit?', '["Olympics", "competition", "athlete", "medal"]', '讨论奥运会和体育精神'),
('sports', 'Fitness', 'A2', 'Do you exercise regularly? What kind of exercise do you prefer?', '["fitness", "exercise", "gym", "workout"]', '讨论健身和运动习惯'),
('sports', 'Esports', 'B1', 'What do you think about esports? Do you consider it a real sport?', '["esports", "gaming", "competition", "professional"]', '讨论电子竞技和游戏竞技'),

-- 旅游类
('travel', 'Travel Plans', 'A2', 'Where would you like to travel? What places are on your travel bucket list?', '["travel", "vacation", "destination", "trip"]', '讨论旅行计划和目的地'),
('travel', 'Travel Experiences', 'B1', 'What is the most memorable trip you have taken? What made it special?', '["travel", "experience", "memory", "adventure"]', '讨论旅行经历和回忆'),
('travel', 'Culture', 'B2', 'Have you experienced culture shock while traveling? How do you adapt to different cultures?', '["culture", "tradition", "custom", "local"]', '讨论旅行中的文化体验'),
('travel', 'Food', 'B1', 'What is your favorite cuisine? Have you tried any exotic foods while traveling?', '["food", "cuisine", "restaurant", "local food"]', '讨论旅行中的美食体验'),
('travel', 'Budget Travel', 'B1', 'How do you plan a budget-friendly trip? What are your money-saving travel tips?', '["budget", "money", "cheap", "tips"]', '讨论预算旅行和省钱技巧'),

-- 娱乐类
('entertainment', 'Movies', 'A2', 'What is your favorite movie? What type of movies do you enjoy?', '["movie", "film", "cinema", "actor"]', '讨论电影和观影体验'),
('entertainment', 'Music', 'A2', 'What kind of music do you like? Who is your favorite artist?', '["music", "song", "artist", "concert"]', '讨论音乐和艺术家'),
('entertainment', 'Books', 'B1', 'Do you like reading? What is the best book you have read recently?', '["book", "reading", "novel", "author"]', '讨论书籍和阅读'),
('entertainment', 'TV Shows', 'A2', 'What TV shows are you watching now? Do you prefer dramas or comedies?', '["TV", "show", "series", "episode"]', '讨论电视剧和节目'),
('entertainment', 'Streaming', 'B1', 'What streaming platforms do you use? How has streaming changed entertainment?', '["streaming", "Netflix", "platform", "content"]', '讨论流媒体和在线娱乐'),

-- 生活类
('lifestyle', 'Daily Routine', 'A1', 'What is your typical day like? What time do you usually wake up?', '["routine", "daily", "schedule", "morning"]', '讨论日常生活和作息'),
('lifestyle', 'Hobbies', 'A2', 'What are your hobbies? How do you spend your free time?', '["hobby", "interest", "leisure", "free time"]', '讨论兴趣爱好和休闲活动'),
('lifestyle', 'Shopping', 'A2', 'Do you like shopping? Do you prefer online or in-store shopping?', '["shopping", "buy", "store", "online"]', '讨论购物和消费习惯'),
('lifestyle', 'Cooking', 'A2', 'Do you like cooking? What is your favorite dish to make?', '["cooking", "recipe", "food", "kitchen"]', '讨论烹饪和美食'),
('lifestyle', 'Fashion', 'B1', 'How important is fashion to you? What is your style?', '["fashion", "style", "clothing", "trend"]', '讨论时尚和穿衣风格'),

-- 工作类
('work', 'Career', 'B1', 'What is your dream job? What career path are you interested in?', '["career", "job", "profession", "future"]', '讨论职业和职业规划'),
('work', 'Workplace', 'B1', 'What do you think makes a good workplace? How do you handle work stress?', '["workplace", "office", "colleague", "stress"]', '讨论工作环境和职场'),
('work', 'Remote Work', 'B2', 'What do you think about remote work? What are its advantages and disadvantages?', '["remote work", "home office", "flexibility", "productivity"]', '讨论远程工作和灵活性'),
('work', 'Entrepreneurship', 'B2', 'Have you ever thought about starting your own business? What challenges would you face?', '["business", "startup", "entrepreneur", "challenge"]', '讨论创业和商业'),
('work', 'Skills', 'B1', 'What skills do you think are most important in today''s job market?', '["skill", "ability", "competence", "market"]', '讨论技能和职场竞争力'),

-- 学习类
('learning', 'Language Learning', 'B1', 'How do you learn English? What methods work best for you?', '["language", "learning", "method", "practice"]', '讨论语言学习和方法'),
('learning', 'Online Courses', 'B1', 'Have you taken any online courses? What are the pros and cons?', '["online course", "education", "platform", "certificate"]', '讨论在线课程和学习平台'),
('learning', 'Study Tips', 'A2', 'What are your study habits? How do you stay motivated?', '["study", "habit", "motivation", "technique"]', '讨论学习习惯和技巧'),
('learning', 'Memory', 'B1', 'How do you improve your memory? What techniques do you use?', '["memory", "remember", "technique", "brain"]', '讨论记忆力和学习方法'),
('learning', 'Certification', 'B2', 'Are certifications important for your career? What certifications do you have?', '["certification", "qualification", "credential", "career"]', '讨论证书和资质');

