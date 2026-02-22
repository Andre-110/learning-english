"""
OpenAI Realtime API WebSocket 端点

实现真正的端到端语音对话：
- 音频直接发送到 OpenAI
- OpenAI 直接返回音频响应
- 无需单独的 STT/TTS 步骤
- 超低延迟
"""
import asyncio
import base64
import json
import time
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from services.openai_realtime import (
    OpenAIRealtimeService, 
    RealtimeConfig,
    RealtimeEventType
)
from services.utils.logger import get_logger
from prompts.templates import SystemPrompt

logger = get_logger("api.realtime")
router = APIRouter()


def get_english_tutor_instructions(user_level: str = "B1") -> str:
    """获取英语教练指令"""
    return f"""You are LinguaCoach, a friendly and encouraging English language tutor specialized in conversational practice.

## Your Role
You help users practice spoken English through natural, engaging conversations. The current user's estimated level is {user_level} (CEFR scale).

## Guidelines

### Conversation Style
- Be warm, patient, and encouraging
- Keep responses concise (2-3 sentences max) to maintain natural conversation flow
- Ask follow-up questions to keep the conversation going
- Show genuine interest in what the user says

### Language Adaptation
- Match your vocabulary and grammar complexity to the user's level ({user_level})
- For lower levels (A1-A2): Use simple words, short sentences, speak slowly
- For intermediate (B1-B2): Use varied vocabulary, moderate complexity
- For advanced (C1-C2): Use natural, native-like speech with idioms

### Error Handling
- If the user makes minor errors, don't interrupt - focus on communication
- For significant errors that affect meaning, gently rephrase correctly
- Occasionally provide helpful vocabulary or expressions naturally

### Topic Management
- Follow the user's lead on topics
- If they want to change topics, go with it enthusiastically
- If conversation stalls, suggest interesting topics based on their interests

### Feedback Style
- Give positive reinforcement for good expressions
- Be specific with praise ("Great use of the past tense!")
- Make corrections feel like helpful suggestions, not criticisms

Remember: Your goal is to build confidence and make English practice enjoyable!"""


@router.websocket("/ws/realtime")
async def realtime_voice_chat(
    websocket: WebSocket,
    user_level: str = Query(default="B1", description="用户CEFR等级")
):
    """
    OpenAI Realtime API 语音聊天端点
    
    协议:
    - 客户端发送: {"type": "audio", "data": "<base64 PCM16 audio>"}
    - 客户端发送: {"type": "end_turn"} 结束发言
    - 客户端发送: {"type": "text", "text": "..."} 发送文本
    - 客户端发送: {"type": "cancel"} 取消当前响应
    
    - 服务端发送: {"type": "audio", "data": "<base64 PCM16 audio>"}
    - 服务端发送: {"type": "transcript", "text": "...", "role": "user|assistant"}
    - 服务端发送: {"type": "response_done", "text": "..."}
    - 服务端发送: {"type": "error", "message": "..."}
    - 服务端发送: {"type": "status", "status": "connected|speaking|processing"}
    """
    await websocket.accept()
    logger.info(f"Realtime WebSocket 连接已建立, user_level={user_level}")
    
    # 创建 Realtime 服务
    config = RealtimeConfig(
        voice="alloy",
        instructions=get_english_tutor_instructions(user_level),
        temperature=0.8
    )
    realtime_service = OpenAIRealtimeService(config=config)
    
    # 连接计时
    connect_start = time.time()
    
    try:
        # 连接到 OpenAI Realtime API
        if not await realtime_service.connect():
            await websocket.send_json({
                "type": "error",
                "message": "无法连接到 OpenAI Realtime API"
            })
            await websocket.close()
            return
        
        connect_time = time.time() - connect_start
        logger.info(f"Realtime API 连接耗时: {connect_time:.2f}秒")
        
        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "message": "已连接到 Realtime API"
        })
        
        # 用于存储当前响应
        current_transcript = ""
        response_start_time = None
        first_audio_time = None
        
        # 创建任务来处理双向通信
        async def handle_client_messages():
            """处理来自客户端的消息"""
            nonlocal response_start_time
            
            try:
                while True:
                    data = await websocket.receive_json()
                    msg_type = data.get("type")
                    
                    if msg_type == "audio":
                        # 接收音频数据
                        audio_base64 = data.get("data", "")
                        if audio_base64:
                            audio_data = base64.b64decode(audio_base64)
                            await realtime_service.send_audio(audio_data)
                    
                    elif msg_type == "end_turn":
                        # 用户结束发言
                        logger.info("用户结束发言，请求AI响应")
                        response_start_time = time.time()
                        await realtime_service.commit_audio()
                        await realtime_service.create_response()
                        
                        await websocket.send_json({
                            "type": "status",
                            "status": "processing"
                        })
                    
                    elif msg_type == "text":
                        # 文本消息
                        text = data.get("text", "")
                        if text:
                            await realtime_service.send_text(text)
                            response_start_time = time.time()
                            await realtime_service.create_response()
                    
                    elif msg_type == "cancel":
                        # 取消响应
                        await realtime_service.cancel_response()
                    
                    elif msg_type == "ping":
                        # 心跳
                        await websocket.send_json({"type": "pong"})
                        
            except WebSocketDisconnect:
                logger.info("客户端断开连接")
            except Exception as e:
                logger.error(f"处理客户端消息错误: {e}")
        
        async def handle_realtime_events():
            """处理来自 OpenAI Realtime API 的事件"""
            nonlocal current_transcript, first_audio_time
            
            try:
                async for event in realtime_service.listen():
                    event_type = event.get("type", "")
                    
                    if event_type == "response.audio.delta":
                        # 音频增量 - 直接转发给客户端
                        audio_base64 = event.get("delta", "")
                        if audio_base64:
                            # 记录首个音频时间
                            if first_audio_time is None and response_start_time:
                                first_audio_time = time.time()
                                latency = first_audio_time - response_start_time
                                logger.info(f"首个音频延迟: {latency:.2f}秒")
                            
                            await websocket.send_json({
                                "type": "audio",
                                "data": audio_base64
                            })
                    
                    elif event_type == "response.audio_transcript.delta":
                        # AI响应的转录增量
                        transcript = event.get("delta", "")
                        if transcript:
                            current_transcript += transcript
                            await websocket.send_json({
                                "type": "transcript",
                                "text": transcript,
                                "role": "assistant",
                                "is_delta": True
                            })
                    
                    elif event_type == "conversation.item.input_audio_transcription.completed":
                        # 用户语音转录完成
                        transcript = event.get("transcript", "")
                        if transcript:
                            await websocket.send_json({
                                "type": "transcript",
                                "text": transcript,
                                "role": "user",
                                "is_delta": False
                            })
                            logger.info(f"用户说: {transcript[:100]}...")
                    
                    elif event_type == "response.done":
                        # 响应完成
                        response = event.get("response", {})
                        
                        # 计算总延迟
                        if response_start_time:
                            total_time = time.time() - response_start_time
                            logger.info(f"响应总耗时: {total_time:.2f}秒")
                        
                        await websocket.send_json({
                            "type": "response_done",
                            "text": current_transcript
                        })
                        
                        # 重置状态
                        current_transcript = ""
                        first_audio_time = None
                    
                    elif event_type == "input_audio_buffer.speech_started":
                        # 检测到用户开始说话
                        await websocket.send_json({
                            "type": "status",
                            "status": "speaking"
                        })
                    
                    elif event_type == "input_audio_buffer.speech_stopped":
                        # 检测到用户停止说话
                        await websocket.send_json({
                            "type": "status",
                            "status": "processing"
                        })
                    
                    elif event_type == "error":
                        # 错误
                        error = event.get("error", {})
                        error_msg = error.get("message", "Unknown error")
                        logger.error(f"Realtime API 错误: {error_msg}")
                        
                        await websocket.send_json({
                            "type": "error",
                            "message": error_msg
                        })
                    
                    elif event_type == "rate_limits.updated":
                        # 速率限制信息
                        rate_limits = event.get("rate_limits", [])
                        logger.debug(f"速率限制更新: {rate_limits}")
                        
            except Exception as e:
                logger.error(f"处理 Realtime 事件错误: {e}")
        
        # 并行运行两个任务
        client_task = asyncio.create_task(handle_client_messages())
        realtime_task = asyncio.create_task(handle_realtime_events())
        
        # 等待任一任务完成（通常是客户端断开）
        done, pending = await asyncio.wait(
            [client_task, realtime_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # 取消未完成的任务
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开")
    except Exception as e:
        logger.error(f"Realtime 端点错误: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        # 清理连接
        await realtime_service.disconnect()
        logger.info("Realtime 会话已结束")


@router.get("/realtime/info")
async def get_realtime_info():
    """获取 Realtime API 信息"""
    return {
        "endpoint": "/ws/realtime",
        "description": "OpenAI Realtime API - 端到端语音对话",
        "features": [
            "直接音频输入/输出，无需单独STT/TTS",
            "超低延迟（约500ms首音频）",
            "服务端VAD（语音活动检测）",
            "实时转录",
            "自然对话流"
        ],
        "audio_format": {
            "input": "PCM16, 24kHz, mono",
            "output": "PCM16, 24kHz, mono"
        },
        "protocol": {
            "client_messages": [
                {"type": "audio", "data": "<base64 PCM16>"},
                {"type": "end_turn"},
                {"type": "text", "text": "..."},
                {"type": "cancel"},
                {"type": "ping"}
            ],
            "server_messages": [
                {"type": "audio", "data": "<base64 PCM16>"},
                {"type": "transcript", "text": "...", "role": "user|assistant"},
                {"type": "response_done", "text": "..."},
                {"type": "status", "status": "connected|speaking|processing"},
                {"type": "error", "message": "..."},
                {"type": "pong"}
            ]
        }
    }

