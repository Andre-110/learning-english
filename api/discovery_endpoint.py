"""
每日发现 WebSocket 端点 - Live Learning Pipeline

实时流水线：
1. 接收用户话题选择
2. 使用 GPT-4o + web_search 搜索真实新闻
3. LLM 改写适配用户等级
4. 返回结构化的文章内容 + 练习题
5. 支持基于文章的对话交互
6. 支持文章和交互历史存储
7. 支持生词本功能
8. 支持文章翻译

核心技术：
- OpenAI Responses API + web_search_preview 工具（联网搜索真实新闻）
- GPT-4o 改写和出题
- WebSocket 实时状态推送
- Supabase 数据存储
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import Response
from typing import Optional, List
from datetime import datetime
import json
import asyncio

from openai import OpenAI
from services.utils.logger import get_logger
from storage.discovery_repository import get_discovery_repository
from services.tts import TTSServiceFactory

logger = get_logger("api.discovery")
router = APIRouter(prefix="/discovery", tags=["discovery"])

# OpenAI 客户端配置
# 注意：responses API (web_search) 不支持自定义 base_url，必须使用默认端点
OPENAI_API_KEY = "OPENAI_API_KEY_REMOVED"

# 全局单例
_client = None
_tts_service = None

def get_client():
    """获取 OpenAI 客户端（单例）- 显式使用官方 API 端点以支持 responses API"""
    global _client
    if _client is None:
        logger.info("[Discovery] 创建 OpenAI 客户端（使用官方端点）...")
        # 必须显式设置 base_url 为官方端点，否则 SDK 会从环境变量 OPENAI_BASE_URL 读取代理地址
        # 代理服务（如 yunwu.ai）不支持 responses API (web_search)
        _client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://api.openai.com/v1"  # 强制使用官方端点
        )
    return _client

def get_tts_service():
    """获取 TTS 服务（单例）- 使用 OpenAI TTS"""
    global _tts_service
    if _tts_service is None:
        logger.info("[Discovery] 创建 OpenAI TTS 服务...")
        _tts_service = TTSServiceFactory.create("openai", default_voice="nova")
    return _tts_service


# 话题映射
TOPIC_MAP = {
    "tech": "Technology and Innovation",
    "health": "Health and Wellness", 
    "culture": "Culture and Arts",
    "business": "Business and Finance",
    "travel": "Travel and Exploration",
    "food": "Food and Cuisine"
}

TOPIC_SEARCH_KEYWORDS = {
    "tech": "latest technology news AI robotics gadgets",
    "health": "health wellness medical breakthrough fitness",
    "culture": "art culture entertainment movies music",
    "business": "business finance economy startup investment",
    "travel": "travel tourism destinations vacation",
    "food": "food cuisine restaurant cooking recipe"
}

# 等级描述
LEVEL_DESCRIPTIONS = {
    "A1": "very simple vocabulary (100-500 words), short sentences (5-8 words), basic present tense only",
    "A2": "simple vocabulary (500-1000 words), short sentences (8-12 words), present and past tense",
    "B1": "intermediate vocabulary (1000-2000 words), moderate complexity (12-18 words), common idioms",
    "B2": "upper-intermediate vocabulary (2000-4000 words), complex sentences (15-25 words), varied grammar",
    "C1": "advanced vocabulary (4000-8000 words), sophisticated structures, nuanced expressions",
    "C2": "native-level vocabulary, complex academic language, subtle nuances"
}


def search_real_news_sync(client: OpenAI, topic: str, custom_topic: str = None) -> str:
    """
    同步版本：使用 GPT-4o + web_search 搜索真实新闻
    
    Args:
        client: OpenAI 客户端
        topic: 预设话题 ID（如 tech, health）或 'custom'
        custom_topic: 自定义话题文本（当 topic='custom' 时使用）
    """
    if topic == 'custom' and custom_topic:
        topic_name = custom_topic
        logger.info(f"[Discovery] 搜索自定义话题: {topic_name}")
    else:
        topic_name = TOPIC_MAP.get(topic, topic)
        logger.info(f"[Discovery] 搜索预设话题: {topic_name}")
    
    logger.info(f"[Discovery] Client base_url: {client.base_url}")
    
    response = client.responses.create(
        model="gpt-4o",
        tools=[{"type": "web_search_preview"}],
        input=f"Search for the latest {topic_name} news. Find ONE interesting and educational news article. Return the full article content including title, source, and main text."
    )
    
    logger.info(f"[Discovery] Response type: {type(response)}")
    
    # 如果返回的是字符串（某些情况下会发生），直接返回
    if isinstance(response, str):
        logger.warning(f"[Discovery] Response 是字符串，长度: {len(response)}")
        return response
    
    # 提取搜索结果文本
    for output in response.output:
        if hasattr(output, 'content'):
            for content in output.content:
                if hasattr(content, 'text'):
                    return content.text
    
    return ""


async def search_real_news(client: OpenAI, topic: str, custom_topic: str = None) -> str:
    """
    Step 1: 使用 GPT-4o + web_search 搜索真实新闻（异步包装）
    
    返回搜索到的新闻原文
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: search_real_news_sync(client, topic, custom_topic)
    )


def adapt_article_sync(client: OpenAI, raw_news: str, cefr_level: str, topic: str) -> dict:
    """
    同步版本：改写文章适配用户等级 + 生成练习题
    """
    level_desc = LEVEL_DESCRIPTIONS.get(cefr_level, LEVEL_DESCRIPTIONS["B1"])
    
    prompt = f"""Based on this real news article, create an educational reading material for English learners.

ORIGINAL NEWS:
{raw_news[:3000]}

TARGET LEVEL: CEFR {cefr_level}
Level requirements: {level_desc}

TASK:
1. Rewrite the news into a simplified version suitable for {cefr_level} learners (150-200 words)
2. Also provide the original/advanced version (200-250 words)
3. Select 3-5 key vocabulary words with pronunciation and bilingual definitions
4. Create ONE comprehension quiz question with 4 options
5. Identify ONE grammar point demonstrated in the article

OUTPUT FORMAT (JSON only, no markdown):
{{
    "title": "Article title",
    "source": "Original news source if available",
    "simplified_content": [
        "First paragraph for {cefr_level} learners",
        "Second paragraph"
    ],
    "original_content": [
        "First paragraph - more advanced",
        "Second paragraph"
    ],
    "vocabulary": [
        {{"word": "example", "phonetic": "/ɪɡˈzæmpəl/", "definition": "n. 例子；a representative instance"}}
    ],
    "quiz": {{
        "question": "What is the main point of this article?",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "answer_index": 0,
        "explanation": "Explanation of correct answer"
    }},
    "grammar_focus": {{
        "point": "Grammar point name",
        "explanation": "Brief explanation",
        "example": "Example sentence from article"
    }}
}}"""

    logger.info(f"[Discovery] 改写文章: level={cefr_level}")
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert English teacher. Output valid JSON only, no markdown."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=2000,
        response_format={"type": "json_object"}
    )
    
    result_text = response.choices[0].message.content.strip()
    return json.loads(result_text)


async def adapt_article_for_level(client: OpenAI, raw_news: str, cefr_level: str, topic: str) -> dict:
    """
    Step 2 & 3: 改写文章适配用户等级 + 生成练习题（异步包装）
    
    返回结构化的文章数据
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        adapt_article_sync,
        client,
        raw_news,
        cefr_level,
        topic
    )


def get_chat_prompt(article_title: str, article_content: str) -> str:
    """生成对话的 system prompt"""
    return f"""You are a friendly English tutor helping a student understand an article they just read.

Article Title: {article_title}
Article Content: {article_content}

Your role:
1. Answer questions about the article content clearly
2. Explain vocabulary and grammar in simple terms
3. Use a mix of English (primary) and Chinese (for key explanations)
4. Keep responses concise (2-4 sentences)
5. Encourage the student

If the student's question is unrelated to the article, gently guide them back to the topic."""


# ========== REST API 端点 ==========

@router.get("/articles")
async def get_user_articles(user_id: str, limit: int = 20):
    """获取用户的历史文章列表"""
    try:
        repo = get_discovery_repository()
        articles = repo.get_user_articles(user_id, limit)
        return {"articles": articles}
    except Exception as e:
        logger.error(f"[Discovery] 获取文章列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/articles/{article_id}")
async def get_article_detail(article_id: str):
    """获取文章详情（包含交互历史）"""
    try:
        repo = get_discovery_repository()
        article = repo.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="文章不存在")
        
        # 获取交互历史
        interactions = repo.get_article_interactions(article_id)
        article["interactions"] = interactions
        
        return article
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Discovery] 获取文章详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vocabulary")
async def get_user_vocabulary(user_id: str, mastery_level: int = None, limit: int = 100):
    """获取用户生词本"""
    try:
        repo = get_discovery_repository()
        vocabulary = repo.get_user_vocabulary(user_id, mastery_level, limit)
        return {"vocabulary": vocabulary}
    except Exception as e:
        logger.error(f"[Discovery] 获取生词本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vocabulary")
async def add_vocabulary(user_id: str, word_data: dict):
    """添加单词到生词本"""
    try:
        repo = get_discovery_repository()
        success = repo.add_vocabulary(user_id, word_data)
        if success:
            return {"status": "success", "message": "已添加到生词本"}
        else:
            raise HTTPException(status_code=500, detail="添加失败")
    except Exception as e:
        logger.error(f"[Discovery] 添加生词失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vocabulary/{word}")
async def remove_vocabulary(user_id: str, word: str):
    """从生词本移除单词"""
    try:
        repo = get_discovery_repository()
        success = repo.remove_vocabulary(user_id, word)
        if success:
            return {"status": "success", "message": "已从生词本移除"}
        else:
            raise HTTPException(status_code=500, detail="移除失败")
    except Exception as e:
        logger.error(f"[Discovery] 移除生词失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/translate")
async def translate_text(text: str, target_lang: str = "zh"):
    """翻译文本"""
    try:
        client = get_client()
        
        def translate_sync():
            return client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"You are a translator. Translate the following text to {'Chinese' if target_lang == 'zh' else 'English'}. Only output the translation, nothing else."},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=1000
            )
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, translate_sync)
        translation = response.choices[0].message.content.strip()
        
        return {"original": text, "translation": translation, "target_lang": target_lang}
    except Exception as e:
        logger.error(f"[Discovery] 翻译失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== WebSocket 端点 ==========

@router.websocket("/ws")
async def discovery_websocket(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None)
):
    """
    每日发现 WebSocket 端点
    
    消息格式：
    客户端 -> 服务端:
        {"type": "get_article", "topic": "tech", "cefr_level": "B1"}
        {"type": "chat", "message": "What does this word mean?"}
        {"type": "submit_quiz", "answer_index": 0}
    
    服务端 -> 客户端:
        {"type": "connected"}
        {"type": "status", "step": 1, "message": "正在搜索最新新闻..."}
        {"type": "status", "step": 2, "message": "正在适配难度..."}
        {"type": "status", "step": 3, "message": "正在生成练习..."}
        {"type": "article", "data": {...}}
        {"type": "chat_response", "message": "..."}
        {"type": "quiz_result", "correct": true, "explanation": "..."}
        {"type": "error", "message": "..."}
    """
    await websocket.accept()
    logger.info(f"[Discovery] WebSocket 连接, user_id={user_id}")
    
    # 获取 OpenAI 客户端
    client = get_client()
    
    # 获取存储仓库
    repo = get_discovery_repository()
    
    # 当前文章上下文（用于对话）
    current_article = None
    current_article_id = None  # 数据库中的文章ID
    
    # 发送连接成功
    await websocket.send_json({"type": "connected"})
    
    try:
        while True:
            message = await websocket.receive()
            
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "get_article":
                        # ========== 文章生成流水线 ==========
                        topic = data.get("topic", "tech")
                        custom_topic = data.get("custom_topic")  # 自定义话题文本
                        cefr_level = data.get("cefr_level", "B1")
                        
                        # 确定搜索的话题名称（用于显示）
                        display_topic = custom_topic if topic == "custom" else TOPIC_MAP.get(topic, topic)
                        
                        logger.info(f"[Discovery] 请求文章: topic={topic}, custom={custom_topic}, level={cefr_level}")
                        
                        try:
                            # Step 1: 搜索真实新闻
                            await websocket.send_json({
                                "type": "status",
                                "step": 1,
                                "message": f"正在搜索「{display_topic}」相关内容..."
                            })
                            
                            raw_news = await search_real_news(client, topic, custom_topic)
                            
                            if not raw_news:
                                raise Exception("未找到相关新闻")
                            
                            logger.info(f"[Discovery] 搜索到新闻: {len(raw_news)} 字符")
                            
                            # Step 2: 适配难度
                            await websocket.send_json({
                                "type": "status",
                                "step": 2,
                                "message": f"正在适配 {cefr_level} 难度..."
                            })
                            
                            # Step 3: 生成练习（与 Step 2 合并）
                            await websocket.send_json({
                                "type": "status",
                                "step": 3,
                                "message": "正在生成练习题..."
                            })
                            
                            article_data = await adapt_article_for_level(client, raw_news, cefr_level, topic)
                            
                            # 保存当前文章上下文
                            current_article = article_data
                            current_article["topic"] = topic
                            current_article["custom_topic"] = custom_topic
                            current_article["cefr_level"] = cefr_level
                            
                            # 保存到数据库
                            if user_id:
                                try:
                                    current_article_id = repo.save_article(user_id, current_article)
                                    logger.info(f"[Discovery] 文章已保存: {current_article_id}")
                                except Exception as save_err:
                                    logger.warning(f"[Discovery] 保存文章失败（继续运行）: {save_err}")
                            
                            # 发送文章数据
                            await websocket.send_json({
                                "type": "article",
                                "data": {
                                    "article_id": current_article_id,  # 返回文章ID
                                    "title": article_data.get("title", "Untitled"),
                                    "source": article_data.get("source", ""),
                                    "simplified_content": article_data.get("simplified_content", []),
                                    "original_content": article_data.get("original_content", []),
                                    "vocabulary": article_data.get("vocabulary", []),
                                    "quiz": article_data.get("quiz"),
                                    "grammar_focus": article_data.get("grammar_focus"),
                                    "topic": topic,
                                    "custom_topic": custom_topic,
                                    "cefr_level": cefr_level
                                }
                            })
                            
                            logger.info(f"[Discovery] 文章生成成功: {article_data.get('title', '')[:50]}")
                            
                        except Exception as e:
                            logger.error(f"[Discovery] 文章生成失败: {e}")
                            await websocket.send_json({
                                "type": "error",
                                "message": f"生成失败: {str(e)}"
                            })
                    
                    elif msg_type == "chat":
                        # ========== 文章对话 ==========
                        user_message = data.get("message", "")
                        
                        if not current_article:
                            await websocket.send_json({
                                "type": "chat_response",
                                "message": "请先选择一篇文章阅读。"
                            })
                            continue
                        
                        # 构建上下文
                        article_content = "\n\n".join(current_article.get("simplified_content", []))
                        system_prompt = get_chat_prompt(
                            current_article.get("title", ""),
                            article_content
                        )
                        
                        try:
                            def chat_sync():
                                return client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=[
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": user_message}
                                    ],
                                    temperature=0.7,
                                    max_tokens=300
                                )
                            
                            loop = asyncio.get_event_loop()
                            response = await loop.run_in_executor(None, chat_sync)
                            
                            reply = response.choices[0].message.content.strip()
                            
                            # 保存对话交互
                            if user_id and current_article_id:
                                try:
                                    repo.save_interaction(user_id, current_article_id, "chat", {
                                        "user_message": user_message,
                                        "ai_response": reply
                                    })
                                except Exception as save_err:
                                    logger.warning(f"[Discovery] 保存对话失败: {save_err}")
                            
                            await websocket.send_json({
                                "type": "chat_response",
                                "message": reply
                            })
                            
                        except Exception as e:
                            logger.error(f"[Discovery] 对话失败: {e}")
                            await websocket.send_json({
                                "type": "chat_response",
                                "message": "抱歉，我暂时无法回复。请稍后再试。"
                            })
                    
                    elif msg_type == "submit_quiz":
                        # ========== 提交测验答案 ==========
                        answer_index = data.get("answer_index", -1)
                        
                        if not current_article or not current_article.get("quiz"):
                            await websocket.send_json({
                                "type": "quiz_result",
                                "correct": False,
                                "explanation": "没有可用的测验题目"
                            })
                            continue
                        
                        quiz = current_article["quiz"]
                        correct_index = quiz.get("answer_index", 0)
                        is_correct = answer_index == correct_index
                        
                        # 保存测验结果
                        if user_id and current_article_id:
                            try:
                                repo.save_interaction(user_id, current_article_id, "quiz", {
                                    "question": quiz.get("question"),
                                    "user_answer": answer_index,
                                    "correct_answer": correct_index,
                                    "is_correct": is_correct
                                })
                            except Exception as save_err:
                                logger.warning(f"[Discovery] 保存测验结果失败: {save_err}")
                        
                        await websocket.send_json({
                            "type": "quiz_result",
                            "correct": is_correct,
                            "correct_answer": correct_index,
                            "explanation": quiz.get("explanation", "")
                        })
                        
                        if user_id and is_correct:
                            logger.info(f"[Discovery] 用户 {user_id} 答对测验")
                    
                    elif msg_type == "voice_chat":
                        # ========== 语音对话 ==========
                        audio_data = data.get("audio_data", "")
                        audio_format = data.get("format", "wav")
                        
                        if not current_article:
                            await websocket.send_json({
                                "type": "chat_response",
                                "message": "请先选择一篇文章阅读。"
                            })
                            continue
                        
                        if not audio_data:
                            await websocket.send_json({
                                "type": "error",
                                "message": "未收到音频数据"
                            })
                            continue
                        
                        try:
                            import base64
                            import tempfile
                            import os
                            
                            # 解码 base64 音频
                            audio_bytes = base64.b64decode(audio_data)
                            
                            # 保存为临时文件
                            with tempfile.NamedTemporaryFile(suffix=f'.{audio_format}', delete=False) as f:
                                f.write(audio_bytes)
                                temp_path = f.name
                            
                            logger.info(f"[Discovery] 收到语音消息，大小: {len(audio_bytes)} 字节")
                            
                            # 使用 Whisper 进行语音转文字
                            def transcribe_sync():
                                with open(temp_path, 'rb') as audio_file:
                                    return client.audio.transcriptions.create(
                                        model="whisper-1",
                                        file=audio_file,
                                        language="en"
                                    )
                            
                            loop = asyncio.get_event_loop()
                            transcription = await loop.run_in_executor(None, transcribe_sync)
                            user_message = transcription.text.strip()
                            
                            # 删除临时文件
                            os.unlink(temp_path)
                            
                            logger.info(f"[Discovery] 语音转录: {user_message[:50]}...")
                            
                            # 发送转录结果
                            await websocket.send_json({
                                "type": "voice_transcription",
                                "text": user_message
                            })
                            
                            if not user_message:
                                await websocket.send_json({
                                    "type": "chat_response",
                                    "message": "抱歉，我没有听清楚。请再说一遍。"
                                })
                                continue
                            
                            # 构建上下文并进行对话
                            article_content = "\n\n".join(current_article.get("simplified_content", []))
                            system_prompt = get_chat_prompt(
                                current_article.get("title", ""),
                                article_content
                            )
                            
                            def chat_sync():
                                return client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=[
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": user_message}
                                    ],
                                    temperature=0.7,
                                    max_tokens=300
                                )
                            
                            response = await loop.run_in_executor(None, chat_sync)
                            reply = response.choices[0].message.content.strip()
                            
                            # 保存语音对话
                            if user_id and current_article_id:
                                try:
                                    repo.save_interaction(user_id, current_article_id, "voice_chat", {
                                        "transcription": user_message,
                                        "ai_response": reply
                                    })
                                except Exception as save_err:
                                    logger.warning(f"[Discovery] 保存语音对话失败: {save_err}")
                            
                            await websocket.send_json({
                                "type": "chat_response",
                                "message": reply
                            })
                            
                        except Exception as e:
                            logger.error(f"[Discovery] 语音处理失败: {e}")
                            await websocket.send_json({
                                "type": "chat_response",
                                "message": "抱歉，语音处理失败。请稍后再试。"
                            })
                    
                    elif msg_type == "add_vocabulary":
                        # ========== 添加生词 ==========
                        word_data = data.get("word_data", {})
                        
                        if not user_id:
                            await websocket.send_json({
                                "type": "vocabulary_result",
                                "success": False,
                                "message": "请先登录"
                            })
                            continue
                        
                        # 添加来源文章ID
                        if current_article_id:
                            word_data["source_article_id"] = current_article_id
                        
                        try:
                            success = repo.add_vocabulary(user_id, word_data)
                            await websocket.send_json({
                                "type": "vocabulary_result",
                                "success": success,
                                "message": "已添加到生词本" if success else "添加失败",
                                "word": word_data.get("word")
                            })
                        except Exception as e:
                            logger.error(f"[Discovery] 添加生词失败: {e}")
                            await websocket.send_json({
                                "type": "vocabulary_result",
                                "success": False,
                                "message": str(e)
                            })
                    
                    elif msg_type == "translate":
                        # ========== 翻译文本 ==========
                        text = data.get("text", "")
                        target_lang = data.get("target_lang", "zh")
                        
                        if not text:
                            await websocket.send_json({
                                "type": "translation",
                                "success": False,
                                "message": "没有要翻译的文本"
                            })
                            continue
                        
                        try:
                            def translate_sync():
                                return client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=[
                                        {"role": "system", "content": f"You are a translator. Translate the following text to {'Chinese' if target_lang == 'zh' else 'English'}. Only output the translation, nothing else."},
                                        {"role": "user", "content": text}
                                    ],
                                    temperature=0.3,
                                    max_tokens=1000
                                )
                            
                            loop = asyncio.get_event_loop()
                            response = await loop.run_in_executor(None, translate_sync)
                            translation = response.choices[0].message.content.strip()
                            
                            await websocket.send_json({
                                "type": "translation",
                                "success": True,
                                "original": text,
                                "translation": translation,
                                "target_lang": target_lang
                            })
                        except Exception as e:
                            logger.error(f"[Discovery] 翻译失败: {e}")
                            await websocket.send_json({
                                "type": "translation",
                                "success": False,
                                "message": str(e)
                            })
                    
                    elif msg_type == "close":
                        break
                        
                except json.JSONDecodeError:
                    logger.warning("[Discovery] 无效的 JSON 消息")
                except Exception as e:
                    logger.error(f"[Discovery] 处理消息错误: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })
    
    except WebSocketDisconnect:
        logger.info(f"[Discovery] WebSocket 断开, user_id={user_id}")
    except Exception as e:
        logger.error(f"[Discovery] WebSocket 错误: {e}")
    finally:
        logger.info(f"[Discovery] 连接关闭, user_id={user_id}")


# ==================== TTS 端点 ====================

from pydantic import BaseModel

class TTSRequest(BaseModel):
    text: str

@router.post("/tts")
async def text_to_speech_post(request: TTSRequest):
    """
    TTS 端点 (POST) - 用于长文本
    
    使用 OpenAI TTS 生成语音音频
    """
    text = request.text[:1000]  # 限制最大长度
    logger.info(f"[Discovery] TTS 请求 (POST): {text[:50]}...")
    
    try:
        tts = get_tts_service()
        audio_data = await tts._text_to_speech_async(text, voice="nova")
        
        return Response(
            content=audio_data,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": 'inline; filename="speech.mp3"',
                "Cache-Control": "no-cache"
            }
        )
    except Exception as e:
        logger.error(f"[Discovery] TTS 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tts/{word}")
async def text_to_speech_get(word: str):
    """
    单词发音 TTS 端点 (GET) - 用于短单词
    
    使用 OpenAI TTS 生成单词发音音频
    """
    # URL 解码并限制长度
    if len(word) > 100:
        raise HTTPException(status_code=400, detail="文本过长，请使用 POST 方法")
    
    logger.info(f"[Discovery] TTS 请求 (GET): {word}")
    
    try:
        tts = get_tts_service()
        audio_data = await tts._text_to_speech_async(word, voice="nova")
        
        return Response(
            content=audio_data,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'inline; filename="word.mp3"',
                "Cache-Control": "public, max-age=86400"
            }
        )
    except Exception as e:
        logger.error(f"[Discovery] TTS 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
