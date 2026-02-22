"""
对话 WebSocket 端点 (精简版)

职责：
1. WebSocket 连接管理
2. 消息路由
3. 调用 tracks 层处理业务逻辑

不包含：
- 业务逻辑（委托给 tracks）
- 评估逻辑（委托给 EvaluationTrack）
- 热点逻辑（委托给 HotContentTrack）
"""
import asyncio
import json
import random
import threading
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from services.tracks import InteractionTrack, EvaluationTrack, HotContentTrack
from services.tracks.hot_content import get_hot_content_track
from storage.repository import RepositoryFactory
from config.constants import (
    WEBSOCKET_RECEIVE_TIMEOUT,
    MIN_AUDIO_SIZE,
    EVALUATION_HISTORY_LIMIT,
)
from services.utils.logger import get_logger

logger = get_logger("api.conversation")
router = APIRouter()

# ==========================================
# 线程安全的单例管理
# ==========================================

_interaction_track: Optional[InteractionTrack] = None
_evaluation_track: Optional[EvaluationTrack] = None
_singleton_lock = threading.Lock()


def get_interaction_track() -> InteractionTrack:
    """获取交互轨单例（线程安全）"""
    global _interaction_track
    if _interaction_track is None:
        with _singleton_lock:
            if _interaction_track is None:
                _interaction_track = InteractionTrack()
    return _interaction_track


def get_evaluation_track() -> EvaluationTrack:
    """获取评估轨单例（线程安全）"""
    global _evaluation_track
    if _evaluation_track is None:
        with _singleton_lock:
            if _evaluation_track is None:
                _evaluation_track = EvaluationTrack()
    return _evaluation_track


# ==========================================
# 全局线程池（复用，避免频繁创建）
# ==========================================

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ws_worker")


@router.websocket("/ws/conversation")
async def conversation_websocket(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None),
    is_continue: bool = Query(False)
):
    """
    对话 WebSocket 端点

    消息协议：
    - 客户端 → 服务端:
      {"type": "start"}          - 开始录音
      {"type": "audio_end"}      - 音频结束
      二进制数据                  - 音频块

    - 服务端 → 客户端:
      {"type": "connected", "initial_question": "..."}  - 连接成功
      {"type": "transcription", "text": "..."}          - 转录结果
      {"type": "text_chunk", "text": "..."}             - AI 回复文本块
      {"type": "audio_chunk", "data": "base64"}         - TTS 音频块
      {"type": "audio_end"}                             - 音频结束
      {"type": "evaluation", "data": {...}}             - 评估结果
      {"type": "error", "message": "..."}               - 错误
    """
    await websocket.accept()
    logger.info(f"[WS] 连接: user_id={user_id}, continue={is_continue}")

    # 初始化
    interaction = get_interaction_track()
    evaluation = get_evaluation_track()
    hot_content = get_hot_content_track()
    user_repo = RepositoryFactory.create_user_repository()

    # 加载用户画像
    user_profile = {}
    if user_id:
        try:
            user_profile = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, user_repo.get_user_profile, user_id
                ),
                timeout=5
            )
            user_profile = user_profile or {}
        except Exception as e:
            logger.warning(f"[WS] 加载用户画像失败: {e}")

    # 对话状态
    conversation_history: List[Dict[str, Any]] = []
    audio_buffer = bytearray()
    pending_hot_content: Optional[Dict[str, Any]] = None

    try:
        # ========== 发送初始问候 ==========
        if not is_continue:
            await _send_greeting(
                websocket, interaction, hot_content, user_profile
            )
        else:
            await websocket.send_json({
                "type": "connected",
                "message": "Connection resumed"
            })

        # ========== 主消息循环 ==========
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=WEBSOCKET_RECEIVE_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.info("[WS] 连接超时")
                break

            # 处理不同消息类型
            if "bytes" in message:
                # 音频数据
                audio_buffer.extend(message["bytes"])

            elif "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type", "")

                if msg_type == "start":
                    audio_buffer.clear()
                    logger.debug("[WS] 开始录音")

                elif msg_type == "audio_end":
                    # 处理音频
                    if len(audio_buffer) < MIN_AUDIO_SIZE:
                        logger.warning(f"[WS] 音频太短: {len(audio_buffer)} bytes")
                        await websocket.send_json({
                            "type": "error",
                            "message": "Audio too short"
                        })
                        continue

                    # 处理用户输入
                    await _process_user_audio(
                        websocket=websocket,
                        audio_data=bytes(audio_buffer),
                        interaction=interaction,
                        evaluation=evaluation,
                        hot_content=hot_content,
                        conversation_history=conversation_history,
                        user_profile=user_profile,
                        user_id=user_id,
                        user_repo=user_repo,
                        pending_hot_content=pending_hot_content
                    )

                    audio_buffer.clear()

            elif message.get("type") == "websocket.disconnect":
                break

    except WebSocketDisconnect:
        logger.info(f"[WS] 断开: user_id={user_id}")
    except Exception as e:
        logger.error(f"[WS] 错误: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()


async def _send_greeting(
    websocket: WebSocket,
    interaction: InteractionTrack,
    hot_content: HotContentTrack,
    user_profile: Dict[str, Any]
):
    """发送开场白（使用 asyncio.Queue 优化）"""
    # 尝试获取热点内容
    hot = await _fetch_greeting_hot_content(hot_content, user_profile)
    hot_dict = hot.to_dict() if hot else None

    # 使用 asyncio.Queue 替代 queue.Queue
    chunk_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def generate():
        """在线程中生成开场白"""
        try:
            for chunk in interaction.generate_greeting(user_profile, hot_dict):
                asyncio.run_coroutine_threadsafe(
                    chunk_queue.put(("chunk", chunk)), loop
                )
            asyncio.run_coroutine_threadsafe(
                chunk_queue.put(("done", None)), loop
            )
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                chunk_queue.put(("error", str(e))), loop
            )

    # 使用全局线程池
    _executor.submit(generate)

    initial_text = ""

    # 异步消费队列（不阻塞事件循环）
    while True:
        try:
            item_type, item = await asyncio.wait_for(
                chunk_queue.get(), timeout=30
            )

            if item_type == "chunk":
                initial_text = await _handle_greeting_chunk(
                    websocket, item, initial_text
                )
            elif item_type == "done":
                break
            elif item_type == "error":
                logger.error(f"[WS] 开场白错误: {item}")
                break

        except asyncio.TimeoutError:
            logger.warning("[WS] 开场白生成超时")
            break

    # 发送连接成功消息
    await websocket.send_json({
        "type": "connected",
        "initial_question": initial_text,
        "has_hot_content": hot is not None
    })


async def _fetch_greeting_hot_content(
    hot_content: HotContentTrack,
    user_profile: Dict[str, Any]
) -> Optional[Any]:
    """获取开场白热点内容"""
    interests = user_profile.get("interests", [])
    if not interests:
        return None

    topic = random.choice(interests)
    try:
        return await hot_content.fetch_for_greeting(
            topic, user_profile.get("cefr_level", "B1")
        )
    except Exception as e:
        logger.warning(f"[WS] 获取开场白热点失败: {e}")
        return None


async def _handle_greeting_chunk(
    websocket: WebSocket,
    chunk: Dict[str, Any],
    initial_text: str
) -> str:
    """处理开场白 chunk"""
    chunk_type = chunk.get("type")
    if chunk_type == "text_chunk":
        initial_text += chunk.get("text", "")
    elif chunk_type in ["audio_chunk", "audio_end"]:
        await websocket.send_json(chunk)
    return initial_text


async def _process_user_audio(
    websocket: WebSocket,
    audio_data: bytes,
    interaction: InteractionTrack,
    evaluation: EvaluationTrack,
    hot_content: HotContentTrack,
    conversation_history: List[Dict[str, Any]],
    user_profile: Dict[str, Any],
    user_id: Optional[str],
    user_repo,
    pending_hot_content: Optional[Dict[str, Any]]
):
    """
    处理用户音频（使用 asyncio.Queue 优化）

    并行执行：
    1. 交互轨：ASR → LLM → TTS
    2. 评估轨：三阶段评估（异步）
    """
    loop = asyncio.get_event_loop()

    # 使用 asyncio.Queue 替代 queue.Queue
    interaction_queue: asyncio.Queue = asyncio.Queue()

    # 用于跨线程共享结果
    result_holder = {"transcription": "", "response": ""}

    def run_interaction():
        """在线程中运行交互轨"""
        try:
            for chunk in interaction.process(
                audio_data=audio_data,
                audio_format="wav",
                conversation_history=conversation_history[-EVALUATION_HISTORY_LIMIT:],
                user_profile=user_profile
            ):
                # 线程安全地放入 asyncio.Queue
                asyncio.run_coroutine_threadsafe(
                    interaction_queue.put(("chunk", chunk)), loop
                )

                # 提取转录和回复
                if chunk.get("type") == "transcription":
                    result_holder["transcription"] = chunk.get("text", "")
                elif chunk.get("type") == "done":
                    result_holder["response"] = chunk.get("response", "")

            asyncio.run_coroutine_threadsafe(
                interaction_queue.put(("done", None)), loop
            )
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                interaction_queue.put(("error", str(e))), loop
            )

    # 使用全局线程池
    _executor.submit(run_interaction)

    # 异步消费队列（不阻塞事件循环）
    while True:
        try:
            item_type, item = await asyncio.wait_for(
                interaction_queue.get(), timeout=60
            )

            if item_type == "chunk":
                await _handle_interaction_chunk(websocket, item)
            elif item_type == "done":
                break
            elif item_type == "error":
                await websocket.send_json({
                    "type": "error",
                    "message": item
                })
                break

        except asyncio.TimeoutError:
            logger.warning("[WS] 交互轨超时")
            break

    # 更新对话历史
    transcription = result_holder["transcription"]
    response_text = result_holder["response"]

    if transcription:
        conversation_history.append({"role": "user", "content": transcription})
    if response_text:
        conversation_history.append({"role": "assistant", "content": response_text})

    # ========== 异步评估轨 ==========
    if transcription:
        asyncio.create_task(
            _run_evaluation_async(
                websocket=websocket,
                evaluation=evaluation,
                hot_content=hot_content,
                transcription=transcription,
                audio_data=audio_data,
                user_profile=user_profile,
                user_id=user_id,
                user_repo=user_repo
            )
        )


async def _handle_interaction_chunk(
    websocket: WebSocket,
    chunk: Dict[str, Any]
):
    """处理交互轨 chunk"""
    chunk_type = chunk.get("type")

    if chunk_type in ["transcription", "text_chunk", "audio_chunk", "audio_end"]:
        await websocket.send_json(chunk)
    elif chunk_type == "done":
        await websocket.send_json({
            "type": "latency",
            "data": chunk.get("latency", {})
        })
    elif chunk_type == "error":
        await websocket.send_json({
            "type": "error",
            "message": chunk.get("message", "Unknown error")
        })


async def _run_evaluation_async(
    websocket: WebSocket,
    evaluation: EvaluationTrack,
    hot_content: HotContentTrack,
    transcription: str,
    audio_data: bytes,
    user_profile: Dict[str, Any],
    user_id: Optional[str],
    user_repo
):
    """异步运行评估轨"""
    try:
        result = await evaluation.evaluate(
            transcription=transcription,
            audio_data=audio_data,
            audio_format="wav",
            user_profile=user_profile
        )

        # 发送评估结果
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({
                "type": "evaluation",
                "data": result.to_dict()
            })

        # 更新用户画像
        if user_id:
            updated_profile = EvaluationTrack.update_user_profile(
                user_profile, result
            )
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: user_repo.update_user_profile(user_id, updated_profile)
                )
            except Exception as e:
                logger.warning(f"[WS] 更新用户画像失败: {e}")

        # 检测兴趣点，触发热点搜索
        if result.interests:
            for interest in result.interests[:2]:  # 最多处理2个
                asyncio.create_task(
                    _search_hot_content_async(
                        hot_content, interest, user_profile.get("cefr_level", "B1")
                    )
                )

    except Exception as e:
        logger.error(f"[WS] 评估轨错误: {e}")


async def _search_hot_content_async(
    hot_content: HotContentTrack,
    topic: str,
    cefr_level: str
):
    """异步搜索热点内容"""
    try:
        result = await hot_content.fetch_for_topic(topic, cefr_level)
        if result:
            logger.info(f"[WS] 热点内容已缓存: {result.headline}")
    except Exception as e:
        logger.warning(f"[WS] 热点搜索失败: {e}")

