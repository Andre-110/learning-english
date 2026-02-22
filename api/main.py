"""
FastAPI主应用入口 - 简化版

核心端点：
1. /auth - 认证
2. /ws/openrouter-audio - OpenRouter Audio（推荐）
3. /streaming-voice/chat - 标准流程（备用）
"""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List


# 兼容 /english 前缀访问（IP 临时入口或反向代理前缀）
class PrefixMiddleware:
    def __init__(self, app, prefix: str = "/english", skip_prefix_paths: Optional[List[str]] = None):
        self.app = app
        self.prefix = prefix
        self.skip_prefix_paths = tuple(skip_prefix_paths or [])

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            path = scope.get("path", "")
            # 对静态资源等路径不做前缀剥离，避免 404
            if self.skip_prefix_paths and path.startswith(self.skip_prefix_paths):
                await self.app(scope, receive, send)
                return
            if path == self.prefix or path.startswith(self.prefix + "/"):
                new_path = path[len(self.prefix):] or "/"
                # 复制 scope，避免修改原始对象
                scope = dict(scope)
                scope["path"] = new_path
                # 记录 root_path，便于生成正确的 URL
                scope["root_path"] = scope.get("root_path", "") + self.prefix
        await self.app(scope, receive, send)
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

from config.settings import Settings
from config.llm_config import llm_config
from storage.repository import RepositoryFactory
from services.utils.logger import setup_logger
from services.utils.system_monitor import start_system_monitor, get_system_summary

# 加载环境变量
load_dotenv()

# ============================================================
# 核心端点导入
# ============================================================

# 1. 认证端点
try:
    from api.auth_endpoint import router as auth_router
    AUTH_ENABLED = True
except ImportError:
    AUTH_ENABLED = False

# 2. 标准流程端点 (STT + LLM + TTS)
try:
    from api.streaming_voice_endpoint import router as streaming_voice_router
    STREAMING_VOICE_ENABLED = True
except ImportError:
    STREAMING_VOICE_ENABLED = False

# 3. OpenRouter Audio端点 (一体化，推荐)
try:
    from api.openrouter_audio_endpoint import router as openrouter_audio_router
    OPENROUTER_AUDIO_ENABLED = True
except ImportError as e:
    OPENROUTER_AUDIO_ENABLED = False
    print(f"OpenRouter Audio端点未启用: {e}")

# 4. Realtime 端点 (Qwen3-Omni Realtime API)
try:
    from api.realtime_endpoint import router as realtime_router
    REALTIME_ENABLED = True
except ImportError as e:
    REALTIME_ENABLED = False
    print(f"Realtime端点未启用: {e}")

# 5. GPT-4o Pipeline 端点 (ASR → LLM → TTS 三段链路)
try:
    from api.gpt4o_pipeline_endpoint import router as gpt4o_pipeline_router
    GPT4O_PIPELINE_ENABLED = True
except ImportError as e:
    GPT4O_PIPELINE_ENABLED = False
    print(f"GPT-4o Pipeline端点未启用: {e}")

# 6. Discovery 端点 (每日发现 - WebSocket 实时流水线)
try:
    from api.discovery_endpoint import router as discovery_router
    DISCOVERY_ENABLED = True
except ImportError as e:
    DISCOVERY_ENABLED = False
    print(f"Discovery端点未启用: {e}")

# 7. 新架构对话端点 (三层架构)
try:
    from api.endpoints.conversation import router as conversation_router
    CONVERSATION_V2_ENABLED = True
except ImportError as e:
    CONVERSATION_V2_ENABLED = False
    print(f"新架构对话端点未启用: {e}")

# 8. 语音风格端点
try:
    from api.voice_style_endpoint import router as voice_style_router
    VOICE_STYLE_ENABLED = True
except ImportError as e:
    VOICE_STYLE_ENABLED = False
    print(f"语音风格端点未启用: {e}")

# 9. 监控端点
try:
    from api.monitoring_endpoint import router as monitoring_router, start_alert_check
    from services.utils.metrics_collector import metrics as metrics_collector
    MONITORING_ENABLED = True
except ImportError as e:
    MONITORING_ENABLED = False
    print(f"监控端点未启用: {e}")

# 10. 日志和时间轴端点
try:
    from api.endpoints.logging import router as logging_router
    LOGGING_ENABLED = True
except ImportError as e:
    LOGGING_ENABLED = False
    print(f"日志端点未启用: {e}")

# 初始化配置
settings = Settings()
logger = setup_logger(level=settings.log_level)

# 启动系统服务器监测（每60秒记录一次）
try:
    system_monitor = start_system_monitor(interval=60)
    logger.info("🖥️ 系统监测已启动（每60秒记录一次）")
except Exception as e:
    logger.warning(f"系统监测启动失败（不影响服务）: {e}")
    system_monitor = None

# 创建FastAPI应用
app = FastAPI(
    title="LinguaCoach API",
    description="基于提示词工程的动态自适应英语对话测评系统",
    version="2.0.0"
)

# 允许以 /english 前缀访问同一套路由（便于 IP 临时访问）
app.add_middleware(
    PrefixMiddleware,
    prefix="/english",
    # 静态资源不剥离前缀，避免 /english/assets 404
    skip_prefix_paths=["/english/assets", "/english/audio"]
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 启动后后台预热（避免阻塞服务启动） ==========
@app.on_event("startup")
async def startup_warmups() -> None:
    loop = asyncio.get_running_loop()

    if STREAMING_VOICE_ENABLED:
        def _warmup_speech():
            try:
                from services.speech_warmup import warmup_speech_service
                logger.info("预热语音服务...")
                warmup_speech_service()
                logger.info("语音服务预热完成")
            except Exception as e:
                logger.warning(f"语音服务预热失败（不影响使用）: {e}")

        loop.run_in_executor(None, _warmup_speech)

    if GPT4O_PIPELINE_ENABLED:
        def _warmup_pipeline():
            try:
                from services.gpt4o_pipeline import GPT4oPipeline
                logger.info("预热 GPT-4o Pipeline 服务...")
                pipeline = GPT4oPipeline()
                pipeline.preload_fillers()
                logger.info("GPT-4o Pipeline 服务预热完成")
            except Exception as e:
                logger.warning(f"GPT-4o Pipeline 预热失败（不影响使用）: {e}")

        loop.run_in_executor(None, _warmup_pipeline)

# ============================================================
# 注册路由
# ============================================================

# 1. 认证端点
if AUTH_ENABLED:
    app.include_router(auth_router)
    logger.info("认证端点已启用")

# 2. 标准流程端点 (STT + LLM + TTS)
if STREAMING_VOICE_ENABLED:
    app.include_router(streaming_voice_router, tags=["streaming-voice"])
    logger.info("标准流程端点已启用 (STT + LLM + TTS)")

# 3. OpenRouter Audio端点 (一体化，推荐)
if OPENROUTER_AUDIO_ENABLED:
    app.include_router(openrouter_audio_router, tags=["openrouter-audio"])
    logger.info("OpenRouter Audio端点已启用 (推荐)")

# 4. Realtime 端点 (Qwen3-Omni Realtime API)
if REALTIME_ENABLED:
    app.include_router(realtime_router, tags=["realtime"])
    logger.info("Realtime端点已启用 (Qwen3-Omni Realtime)")

# 5. GPT-4o Pipeline 端点 (ASR → LLM → TTS)
if GPT4O_PIPELINE_ENABLED:
    app.include_router(gpt4o_pipeline_router, tags=["gpt4o-pipeline"])
    logger.info("GPT-4o Pipeline端点已启用 (ASR → LLM → TTS)")

# 6. Discovery 端点 (每日发现 - 阅读内容)
if DISCOVERY_ENABLED:
    app.include_router(discovery_router, tags=["discovery"])
    logger.info("Discovery端点已启用 (每日发现)")

# 7. 新架构对话端点 (三层架构)
# ⚠️ 已禁用：由 gpt4o_pipeline_router 接管 /ws/conversation
# if CONVERSATION_V2_ENABLED:
#     app.include_router(conversation_router, tags=["conversation-v2"])
#     logger.info("新架构对话端点已启用 (/ws/conversation)")

# 8. 语音风格端点
if VOICE_STYLE_ENABLED:
    app.include_router(voice_style_router, tags=["voice-style"])
    logger.info("语音风格端点已启用 (/voice-style)")

# 9. 监控端点
if MONITORING_ENABLED:
    app.include_router(monitoring_router, tags=["monitoring"])
    # 🆕 /english 前缀别名（用于反向代理前缀路径）
    app.include_router(monitoring_router, prefix="/english", tags=["monitoring"])
    # 启动后台指标聚合和告警检查
    metrics_collector.start_aggregation(interval=60)
    logger.info("📊 监控端点已启用 (/monitoring)")

# 10. 日志和时间轴端点
if LOGGING_ENABLED:
    app.include_router(logging_router, tags=["logging"])
    # 🆕 /english 前缀别名（用于反向代理前缀路径）
    app.include_router(logging_router, prefix="/english", tags=["logging"])
    logger.info("📝 日志端点已启用 (/api/logs)")

# 静态文件服务（Web前端）
static_vue_dir = Path(__file__).parent.parent / "static-vue"

if static_vue_dir.exists():
    # Vue 前端的 assets 目录
    # 🔧 修复：同时挂载 /assets 和 /english/assets 以支持直接访问和 Caddy 代理
    assets_dir = static_vue_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/english/assets", StaticFiles(directory=str(assets_dir)), name="english_assets")

    # 音频预览文件目录
    audio_dir = static_vue_dir / "audio"
    if audio_dir.exists():
        app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

    @app.get("/")
    async def serve_vue_index():
        """提供 Vue 前端页面"""
        index_file = static_vue_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "LinguaCoach API", "version": "2.0.0", "status": "running"}

    @app.get("/english/")
    async def serve_vue_index_english():
        """提供 Vue 前端页面（/english 前缀）"""
        return await serve_vue_index()
    
    @app.get("/monitor")
    async def serve_monitor_page():
        """提供监控仪表盘页面"""
        monitor_file = static_vue_dir / "monitor.html"
        if monitor_file.exists():
            return FileResponse(str(monitor_file))
        return {"message": "Monitor page not found"}

    @app.get("/english/monitor")
    async def serve_monitor_page_english():
        """提供监控仪表盘页面（/english 前缀）"""
        return await serve_monitor_page()

    # VAD 模型文件（.onnx, .wasm, .js）- 使用明确的路由而非通配符
    @app.get("/silero_vad_v5.onnx")
    async def serve_vad_model_v5():
        """提供 VAD v5 模型"""
        return FileResponse(str(static_vue_dir / "silero_vad_v5.onnx"))

    @app.get("/silero_vad_legacy.onnx")
    async def serve_vad_model_legacy():
        """提供 VAD legacy 模型"""
        return FileResponse(str(static_vue_dir / "silero_vad_legacy.onnx"))

    @app.get("/vad.worklet.bundle.min.js")
    async def serve_vad_worklet():
        """提供 VAD worklet"""
        return FileResponse(str(static_vue_dir / "vad.worklet.bundle.min.js"))

    @app.get("/ort-wasm-simd-threaded.wasm")
    async def serve_ort_wasm():
        """提供 ONNX Runtime WASM"""
        return FileResponse(str(static_vue_dir / "ort-wasm-simd-threaded.wasm"))

    @app.get("/ort-wasm-simd-threaded.mjs")
    async def serve_ort_mjs():
        """提供 ONNX Runtime MJS"""
        return FileResponse(str(static_vue_dir / "ort-wasm-simd-threaded.mjs"))

# 全局单例存储
_user_repo = None

def get_user_repo():
    """获取用户存储实例（单例）"""
    global _user_repo
    if _user_repo is None:
        _user_repo = RepositoryFactory.create_user_repository()
    return _user_repo


# ============================================================
# 简化的 API 端点
# ============================================================

@app.get("/api")
async def api_root():
    """API根路径"""
    return {
        "message": "LinguaCoach API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "auth": "/auth" if AUTH_ENABLED else None,
            "openrouter_audio": "/ws/openrouter-audio" if OPENROUTER_AUDIO_ENABLED else None,
            "streaming_voice": "/streaming-voice/chat" if STREAMING_VOICE_ENABLED else None,
            "gpt4o_pipeline": "/ws/gpt4o-pipeline" if GPT4O_PIPELINE_ENABLED else None,
            "conversation_v2": "/ws/conversation" if CONVERSATION_V2_ENABLED else None
        }
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "LinguaCoach"}


@app.get("/system/status")
async def system_status():
    """
    获取系统状态
    
    返回 CPU、内存、磁盘、网络等监测信息
    """
    try:
        from services.utils.system_monitor import get_system_monitor
        monitor = get_system_monitor()
        return {
            "status": "ok",
            **monitor.get_current_status(),
            "alerts": monitor.check_alerts()
        }
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/system/summary")
async def system_summary():
    """
    获取系统状态摘要（轻量级）
    """
    try:
        return {"status": "ok", **get_system_summary()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/users/{user_id}/profile")
async def get_user_profile(user_id: str):
    """获取用户画像"""
    try:
        user_repo = get_user_repo()
        user_profile = user_repo.get(user_id)
        if not user_profile:
            # 创建新用户画像
            from models.user import UserProfile, CEFRLevel
            user_profile = UserProfile(
                user_id=user_id,
                cefr_level=CEFRLevel.A1,
                overall_score=50.0
            )
            user_repo.save(user_profile)
        
        return user_profile.dict()
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/list")
async def list_conversations(user_id: str):
    """获取用户的对话列表"""
    try:
        from storage.impl.supabase_repository import SupabaseConversationRepository
        conv_repo = SupabaseConversationRepository()
        
        # 直接查询数据库获取对话列表（包含评分字段）
        result = conv_repo.client.table("conversations") \
            .select("conversation_id, user_id, started_at, ended_at, state, summary, cefr_level, overall_score") \
            .eq("user_id", user_id) \
            .order("started_at", desc=True) \
            .limit(50) \
            .execute()
        
        conversations = []
        for row in result.data:
            conv_id = row["conversation_id"]
            
            # 直接从 conversations 表获取评分（已在每轮对话后更新）
            cefr_level = row.get("cefr_level") or "A1"
            overall_score = row.get("overall_score") or 0
            
            conversations.append({
                "id": conv_id,
                "created_at": row.get("started_at"),
                "ended_at": row.get("ended_at"),
                "state": row.get("state"),
                "cefr_level": cefr_level,
                "overall_score": round(overall_score, 1) if overall_score else None,
                "title": row.get("summary") or None,
                "first_message": None
            })
        
        return {"conversations": conversations}
    except Exception as e:
        logger.error(f"获取对话列表失败: {e}")
        return {"conversations": []}


@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """获取对话的消息列表"""
    try:
        from storage.impl.supabase_repository import SupabaseConversationRepository
        conv_repo = SupabaseConversationRepository()
        
        # 获取对话基本信息
        conv_result = conv_repo.client.table("conversations") \
            .select("conversation_id, user_id, started_at, summary, state") \
            .eq("conversation_id", conversation_id) \
            .execute()
        
        if not conv_result.data:
            raise HTTPException(status_code=404, detail="对话不存在")
        
        conv_data = conv_result.data[0]
        
        # 获取消息列表
        messages_result = conv_repo.client.table("messages") \
            .select("sender_role, content, timestamp, metadata") \
            .eq("conversation_id", conversation_id) \
            .order("round_number") \
            .order("timestamp") \
            .execute()
        
        messages = []
        pending_assessment = None  # 暂存用户消息的评估，关联到下一条 AI 消息
        
        for msg in messages_result.data:
            # 从 metadata 中提取评估信息
            metadata = msg.get("metadata", {}) or {}
            assessment = metadata.get("assessment") or metadata.get("evaluation")
            
            if msg["sender_role"] == "user":
                # 用户消息：暂存评估，不直接附加
                messages.append({
                    "role": "user",
                    "content": msg["content"],
                    "timestamp": msg.get("timestamp"),
                    "assessment": None
                })
                pending_assessment = assessment
            else:
                # AI 消息：附加上一条用户消息的评估
                messages.append({
                    "role": "assistant",
                    "content": msg["content"],
                    "timestamp": msg.get("timestamp"),
                    "assessment": pending_assessment
                })
                pending_assessment = None  # 清空
        
        return {
            "conversation_id": conversation_id,
            "title": conv_data.get("summary"),
            "state": conv_data.get("state"),
            "created_at": conv_data.get("started_at"),
            "messages": messages
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class StartConversationRequest(BaseModel):
    """开始对话请求"""
    user_id: str


class TranslateRequest(BaseModel):
    """翻译请求"""
    text: str = Field(..., description="要翻译的英文文本")


class FrontendLogRequest(BaseModel):
    """前端日志请求"""
    level: str = Field(..., description="日志级别: info, warning, error")
    type: str = Field(..., description="日志类型: js_error, vue_error, performance, etc.")
    message: str = Field(..., description="日志消息")
    data: Optional[dict] = Field(None, description="额外数据")
    timestamp: Optional[int] = Field(None, description="时间戳")
    url: Optional[str] = Field(None, description="页面 URL")
    userAgent: Optional[str] = Field(None, description="用户代理")


# ============================================================
# 调试录音上传（保存到服务器便于 debug）
# ============================================================
from fastapi import File, Form, UploadFile

DEBUG_RECORDINGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "debug_recordings"
)


@app.post("/api/debug-recording")
async def upload_debug_recording(
    file: UploadFile = File(...),
    user_id: str = Form("unknown"),
    conversation_id: str = Form(""),
):
    """
    接收前端调试录音并保存到服务器
    
    存储位置: {project_root}/debug_recordings/
    文件名: debug-{userId}-{conversationId}-{timestamp}.webm
    """
    try:
        import re
        from datetime import datetime
        
        os.makedirs(DEBUG_RECORDINGS_DIR, exist_ok=True)
        
        uid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(user_id or "unknown"))[:64]
        cid = re.sub(r"[^a-zA-Z0-9_-]", "_", str(conversation_id or ""))[:32]
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        name = f"debug-{uid}-{cid}-{ts}.webm" if cid else f"debug-{uid}-{ts}.webm"
        filepath = os.path.join(DEBUG_RECORDINGS_DIR, name)
        
        with open(filepath, "wb") as f:
            while chunk := await file.read(65536):
                f.write(chunk)
        
        logger.info(f"[调试录音] 已保存: {filepath}")
        return {"status": "ok", "path": filepath, "filename": name}
    except Exception as e:
        logger.error(f"保存调试录音失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/frontend-log")
async def receive_frontend_log(request: FrontendLogRequest):
    """
    接收前端日志上报
    
    用于捕获前端错误、性能指标等
    """
    try:
        import json
        from datetime import datetime
        
        # 构建日志消息
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": request.level,
            "type": request.type,
            "message": request.message,
            "data": request.data,
            "url": request.url,
            "client_timestamp": request.timestamp,
            "user_agent": request.userAgent
        }
        
        # 🆕 写入到 online_logs/frontend/frontend.log
        frontend_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "online_logs", "frontend")
        os.makedirs(frontend_log_dir, exist_ok=True)
        frontend_log_file = os.path.join(frontend_log_dir, "frontend.log")
        
        with open(frontend_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
        
        # 同时记录到应用日志
        if request.level == "error":
            logger.error(f"[前端] 🚨 {request.type}: {request.message} | data={request.data}")
        elif request.level == "warning":
            logger.warning(f"[前端] ⚠️ {request.type}: {request.message} | data={request.data}")
        else:
            logger.info(f"[前端] 📱 {request.type}: {request.message} | data={request.data}")
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"处理前端日志失败: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/translate")
async def translate_text(request: TranslateRequest):
    """
    按需翻译 - 将英文文本翻译成中文
    
    用于用户点击翻译按钮时调用
    """
    try:
        if not request.text or not request.text.strip():
            return {"translation": "", "error": "文本为空"}
        
        # 使用 UnifiedProcessor 进行翻译
        from services.unified_processor import UnifiedProcessor
        processor = UnifiedProcessor(service_type="qwen-omni")
        
        translation = processor.translate_only(request.text.strip())
        
        if translation:
            return {"translation": translation}
        else:
            return {"translation": "", "error": "翻译失败"}
            
    except Exception as e:
        logger.error(f"翻译失败: {e}")
        return {"translation": "", "error": str(e)}


class GenerateSummaryRequest(BaseModel):
    """生成摘要请求"""
    conversation_id: str


@app.post("/conversations/generate-summary")
async def generate_conversation_summary(request: GenerateSummaryRequest):
    """
    为对话生成摘要标题
    
    调用 LLM 根据对话内容生成一句话摘要
    """
    try:
        from storage.impl.supabase_repository import SupabaseConversationRepository
        conv_repo = SupabaseConversationRepository()
        
        # 获取对话消息
        messages_result = conv_repo.client.table("messages") \
            .select("sender_role, content") \
            .eq("conversation_id", request.conversation_id) \
            .order("round_number") \
            .order("timestamp") \
            .limit(10) \
            .execute()
        
        if not messages_result.data:
            return {"summary": None, "message": "对话没有消息"}
        
        # 构建对话内容摘要
        conversation_text = ""
        for msg in messages_result.data[:6]:  # 只取前6条消息
            role = "User" if msg["sender_role"] == "user" else "AI"
            content = msg["content"][:100]  # 截断过长的内容
            conversation_text += f"{role}: {content}\n"
        
        # 调用 LLM 生成摘要
        from services.qwen_omni_audio import create_qwen_omni_service
        
        try:
            llm = create_qwen_omni_service()
            summary = llm.call_with_text(
                system_prompt="You are a helpful assistant. Generate a very short summary (5-10 Chinese characters) for this conversation. Only output the summary, nothing else.",
                user_prompt=f"Summarize this conversation in 5-10 Chinese characters:\n\n{conversation_text}"
            )
            summary = summary.strip().strip('"').strip("'")[:20]  # 限制长度
        except Exception as e:
            logger.warning(f"LLM 生成摘要失败: {e}")
            # 降级：使用第一条用户消息作为标题
            first_user_msg = next((m for m in messages_result.data if m["sender_role"] == "user"), None)
            if first_user_msg:
                summary = first_user_msg["content"][:20] + "..."
            else:
                summary = "英语对话练习"
        
        # 保存摘要到数据库
        conv_repo.client.table("conversations") \
            .update({"summary": summary}) \
            .eq("conversation_id", request.conversation_id) \
            .execute()
        
        logger.info(f"对话摘要已生成: {request.conversation_id} -> {summary}")
        
        return {"summary": summary, "conversation_id": request.conversation_id}
        
    except Exception as e:
        logger.error(f"生成摘要失败: {e}")
        return {"summary": None, "error": str(e)}


@app.post("/conversations/start")
async def start_conversation(request: StartConversationRequest):
    """
    开始新对话
    
    返回 conversation_id，前端用于连接 WebSocket
    """
    import uuid
    from datetime import datetime
    
    # 生成新的对话 ID
    conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
    
    # 获取用户画像以确定初始问题难度
    cefr_level = "A1"
    try:
        user_repo = get_user_repo()
        user_profile = user_repo.get(request.user_id)
        if user_profile:
            cefr_level = str(user_profile.cefr_level.value) if hasattr(user_profile.cefr_level, 'value') else str(user_profile.cefr_level)
    except Exception as e:
        logger.warning(f"获取用户画像失败: {e}")
    
    # 保存对话到数据库
    try:
        from storage.impl.supabase_repository import SupabaseConversationRepository
        conv_repo = SupabaseConversationRepository()
        conv_repo.client.table("conversations").insert({
            "conversation_id": conversation_id,
            "user_id": request.user_id,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "state": "in_progress"
        }).execute()
        logger.info(f"对话已创建: {conversation_id}")
    except Exception as e:
        logger.error(f"保存对话失败: {e}")
    
    return {
        "conversation_id": conversation_id,
        "user_id": request.user_id,
        "cefr_level": cefr_level,
        "created_at": datetime.now().isoformat(),
        "initial_question": None  # 初始问题由 WebSocket 连接时动态生成
    }


# ============================================================
# LLM 服务设置 API
# ============================================================

class LLMServiceRequest(BaseModel):
    """LLM 服务设置请求"""
    service: str = Field(..., description="服务类型: dashscope, qwen-omni 或 openrouter")


# 内存中存储当前服务设置（简化实现，重启后会重置）
_current_llm_service = "gpt4o-pipeline"


@app.get("/settings/llm-service")
async def get_llm_service():
    """获取当前 LLM 服务设置"""
    return {"service": _current_llm_service}


@app.post("/settings/llm-service")
async def set_llm_service(request: LLMServiceRequest):
    """
    设置 LLM 服务
    
    切换后需要重新开始对话才生效
    """
    global _current_llm_service
    
    valid_services = ["gpt4o-pipeline", "qwen-omni", "dashscope", "openrouter", "realtime"]
    if request.service not in valid_services:
        raise HTTPException(status_code=400, detail=f"Invalid service. Must be one of: {valid_services}")
    
    _current_llm_service = request.service
    
    # 重置处理器单例，下次请求时会使用新的服务
    from api.openrouter_audio_endpoint import _processor
    import api.openrouter_audio_endpoint as endpoint_module
    endpoint_module._processor = None
    
    logger.info(f"LLM 服务已切换为: {request.service}")
    
    return {"service": _current_llm_service, "message": "服务已切换，请重新开始对话"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)