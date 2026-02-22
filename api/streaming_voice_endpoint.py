"""
标准流程端点 - 备用的语音对话方式

流程：音频 → STT → 统一处理器 → TTS → 音频
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
from datetime import datetime
import json
import base64
import io
import asyncio
import time
import struct
import wave

from services.speech import SpeechServiceFactory
from services.tts import TTSServiceFactory
from services.unified_processor import UnifiedProcessor, UserProfileUpdater, ProcessingResult, create_processor
from config.settings import Settings
from config.constants import EVALUATION_CADENCE_TURNS, EVALUATION_AGGREGATE_TURNS
from storage.repository import RepositoryFactory
from services.utils.logger import get_logger

logger = get_logger("api.streaming_voice")
router = APIRouter(prefix="/streaming-voice", tags=["streaming-voice"])

settings = Settings()

# 全局单例
_speech_service = None
_tts_service = None
_processor = None


def get_speech_service():
    """获取 STT 服务（单例）"""
    global _speech_service
    if _speech_service is None:
        try:
            from services.speech_warmup import get_warmed_speech_service
            warmed = get_warmed_speech_service()
            if warmed:
                logger.info("[单例] 使用预热的 SpeechService")
                _speech_service = warmed
                return _speech_service
        except ImportError:
            pass
        
        logger.info("[单例] 创建 SpeechService...")
        if settings.speech_provider == "funasr":
            _speech_service = SpeechServiceFactory.create(
                provider="funasr",
                model_dir=settings.funasr_model_dir,
                model_name=settings.funasr_model_name,
                language=settings.funasr_language
            )
        else:
            _speech_service = SpeechServiceFactory.create(provider="whisper")
    return _speech_service


def _aggregate_recent_user_texts(
    conversation_history: list,
    current_text: str,
    max_turns: int
) -> str:
    user_texts = [
        msg.get("content", "").strip()
        for msg in conversation_history
        if msg.get("role") == "user" and isinstance(msg.get("content"), str)
    ]
    if current_text:
        if not user_texts or user_texts[-1] != current_text:
            user_texts.append(current_text)
    if max_turns and max_turns > 0:
        user_texts = user_texts[-max_turns:]
    return " ".join([t for t in user_texts if t]).strip()


def get_tts_service():
    """获取 TTS 服务（单例）"""
    global _tts_service
    if _tts_service is None:
        logger.info("[单例] 创建 TTSService...")
        _tts_service = TTSServiceFactory.create(
            provider=settings.tts_provider,
            model=getattr(settings, 'tts_model', 'gpt-4o-mini-tts'),
            default_voice=getattr(settings, 'tts_default_voice', 'alloy')
        )
    return _tts_service


def get_processor() -> UnifiedProcessor:
    """获取统一处理器（单例）"""
    global _processor
    if _processor is None:
        logger.info("[单例] 创建 UnifiedProcessor...")
        _processor = create_processor()
    return _processor


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> io.BytesIO:
    """将 PCM 数据封装为 WAV 格式"""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    buffer.seek(0)
    return buffer


@router.websocket("/chat")
async def streaming_voice_chat(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None)
):
    """
    标准流程 WebSocket 端点
    
    消息格式同 OpenRouter Audio 端点
    """
    await websocket.accept()
    
    speech_service = get_speech_service()
    tts_service = get_tts_service()
    processor = get_processor()
    user_repo = RepositoryFactory.create_user_repository()
    
    # 加载用户画像
    user_profile = {}
    if user_id:
        db_profile = user_repo.get(user_id)
        if db_profile:
            user_profile = db_profile.dict()
    
    conversation_history = []
    audio_buffer = []
    is_recording = False
    partial_transcript = ""  # 暂存未完成的句子
    
    try:
        # 动态生成初始问题（通过 LLM）
        initial_question = processor.generate_initial_question(user_profile)
        await websocket.send_json({
            "type": "connected",
            "initial_question": initial_question
        })
        
        while True:
            try:
                message = await websocket.receive()
                
                if "text" in message:
                    try:
                        data = json.loads(message["text"])
                        msg_type = data.get("type")
                        
                        if msg_type == "start":
                            is_recording = True
                            audio_buffer = []
                            
                        elif msg_type == "audio_frame":
                            # 处理流式 PCM 音频帧
                            try:
                                # data 是 int16 数组
                                pcm_array = data.get("data", [])
                                if pcm_array and is_recording:
                                    # 打包为 little-endian int16 bytes
                                    byte_data = struct.pack(f'<{len(pcm_array)}h', *pcm_array)
                                    audio_buffer.append(byte_data)
                            except Exception as e:
                                logger.error(f"处理 audio_frame 错误: {e}")

                        elif msg_type == "speculative_stt":
                            # 投机执行：只做 STT，不触发 LLM
                            if audio_buffer and is_recording:
                                partial_transcript = await process_audio(
                                    websocket=websocket,
                                    audio_buffer=audio_buffer,
                                    speech_service=speech_service,
                                    tts_service=tts_service,
                                    processor=processor,
                                    conversation_history=conversation_history,
                                    user_profile=user_profile,
                                    user_id=user_id,
                                    user_repo=user_repo,
                                    partial_transcript=partial_transcript,
                                    speculative=True  # 标记为投机执行
                                )
                                audio_buffer = []  # 已处理音频清空

                        elif msg_type == "confirm_end":
                            # 确认结束：触发 LLM
                            if (audio_buffer or partial_transcript) and is_recording:
                                partial_transcript = await process_audio(
                                    websocket=websocket,
                                    audio_buffer=audio_buffer,
                                    speech_service=speech_service,
                                    tts_service=tts_service,
                                    processor=processor,
                                    conversation_history=conversation_history,
                                    user_profile=user_profile,
                                    user_id=user_id,
                                    user_repo=user_repo,
                                    partial_transcript=partial_transcript,
                                    speculative=False  # 正式执行
                                )
                                audio_buffer = []
                                is_recording = False

                        elif msg_type == "cancel_stt":
                            # 取消投机结果
                            logger.info("[Control] 取消投机结果，继续录音")
                            partial_transcript = ""
                            # 不清空 audio_buffer，因为那是后续的新音频
                        
                        elif msg_type == "audio_end":
                            # 兼容旧模式
                            if audio_buffer and is_recording:
                                partial_transcript = await process_audio(
                                    websocket=websocket,
                                    audio_buffer=audio_buffer,
                                    speech_service=speech_service,
                                    tts_service=tts_service,
                                    processor=processor,
                                    conversation_history=conversation_history,
                                    user_profile=user_profile,
                                    user_id=user_id,
                                    user_repo=user_repo,
                                    partial_transcript=partial_transcript
                                )
                                audio_buffer = []
                                is_recording = False
                        
                        elif msg_type == "close":
                            break
                            
                    except json.JSONDecodeError:
                        pass
                
                elif "bytes" in message:
                    if is_recording:
                        audio_buffer.append(message["bytes"])
                
            except WebSocketDisconnect:
                logger.info("WebSocket 断开")
                break
                
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
    finally:
        # 保存用户画像
        if user_id and user_profile:
            try:
                db_profile = user_repo.get(user_id)
                if db_profile:
                    for key, value in user_profile.items():
                        if hasattr(db_profile, key):
                            setattr(db_profile, key, value)
                    user_repo.save(db_profile)
            except Exception as e:
                logger.error(f"保存用户画像失败: {e}")


async def process_audio(
    websocket: WebSocket,
    audio_buffer: list,
    speech_service,
    tts_service,
    processor: UnifiedProcessor,
    conversation_history: list,
    user_profile: dict,
    user_id: Optional[str],
    user_repo,
    partial_transcript: str = "",
    speculative: bool = False  # 新增参数
) -> str:
    """
    处理音频：STT → 语义判断 → (LLM → TTS)
    
    Args:
        speculative: 是否为投机执行。True 则只做 STT 和语义判断，不触发 LLM。
    
    Returns:
        str: 更新后的 partial_transcript。
    """
    timings = {}
    total_start = time.time()
    
    try:
        # 如果 audio_buffer 为空但有 partial_transcript，说明是 confirm_end 阶段，
        # 且没有新音频，直接使用 partial_transcript 进行 LLM 处理
        if not audio_buffer and partial_transcript and not speculative:
            current_text = partial_transcript
            # 跳过 STT，直接进入后续流程
        else:
            audio_data = b''.join(audio_buffer)
            if not audio_data:
                # 只有在没有任何数据时才报错
                if not partial_transcript:
                    await websocket.send_json({"type": "error", "message": "音频为空"})
                return partial_transcript
            
            logger.info(f"[处理] 音频大小: {len(audio_data)} bytes, speculative={speculative}")
            
            # STT
            await websocket.send_json({"type": "processing", "stage": "stt"})
            
            stt_start = time.time()
            # 将 PCM 数据封装为 WAV
            audio_file = pcm_to_wav(audio_data)
            transcribed_text = speech_service.transcribe_audio(audio_file)
            timings['stt'] = time.time() - stt_start
            
            if not transcribed_text or not transcribed_text.strip():
                return partial_transcript
                
            # 拼接
            current_text = (partial_transcript + " " + transcribed_text).strip()
            logger.info(f"[STT] 识别结果: {transcribed_text}, 当前完整文本: {current_text}")
        
        # 语义完整性判断
        if not processor.is_sentence_complete(current_text):
            logger.info(f"[语义判断] 句子未完成: {current_text}")
            await websocket.send_json({
                "type": "transcription",
                "text": current_text,
                "is_final": False,
                "status": "waiting_for_more"
            })
            return current_text
            
        # 如果是投机执行，到此为止 (只做 ASR + 语义判断)
        if speculative:
            logger.info(f"[投机执行] 完成 STT，暂存结果: {current_text}")
            await websocket.send_json({
                "type": "transcription",
                "text": current_text,
                "is_final": False,
                "status": "speculative_done"
            })
            return current_text

        # 正式执行：发送最终转录并触发 LLM
        await websocket.send_json({
            "type": "transcription",
            "text": current_text,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "is_final": True
        })
        
        # 统一处理器
        await websocket.send_json({"type": "processing", "stage": "llm"})
        
        llm_start = time.time()
        result = processor.process_text(
            user_text=current_text,  # 使用拼接后的完整文本
            conversation_history=conversation_history,
            user_profile=user_profile
        )
        timings['llm'] = time.time() - llm_start
        
        # 更新对话历史
        conversation_history.append({"role": "user", "content": current_text})
        conversation_history.append({"role": "assistant", "content": result.full_response})
        
        if len(conversation_history) > 20:
            conversation_history[:] = conversation_history[-20:]

        # 发送评估（按节奏输出）
        round_count = len(conversation_history) // 2
        if EVALUATION_CADENCE_TURNS > 1 and (round_count % EVALUATION_CADENCE_TURNS) != 0:
            logger.info(f"[评估] 节奏跳过: round={round_count}")
        else:
            aggregated_transcription = _aggregate_recent_user_texts(
                conversation_history,
                current_text,
                EVALUATION_AGGREGATE_TURNS
            )
            if aggregated_transcription:
                evaluation = processor.evaluate_only(
                    transcription=aggregated_transcription,
                    conversation_history=None,
                    user_profile=user_profile
                )
                eval_result = ProcessingResult(
                    transcription=aggregated_transcription,
                    evaluation=evaluation,
                    interests=evaluation.get("interests", []),
                    ai_feedback="",
                    next_question="",
                    full_response=""
                )
                user_profile.update(UserProfileUpdater.update(user_profile, eval_result))
            else:
                evaluation = result.evaluation

            await websocket.send_json({
                "type": "evaluation",
                "data": evaluation
            })
        
        # 发送回复
        await websocket.send_json({
            "type": "response",
            "text": result.full_response,
            "ai_feedback": result.ai_feedback,
            "next_question": result.next_question,
            "interests": result.interests
        })
        
        # TTS
        await websocket.send_json({"type": "processing", "stage": "tts"})
        
        tts_start = time.time()
        await stream_tts(websocket, tts_service, result.full_response)
        timings['tts'] = time.time() - tts_start
        
        total_time = time.time() - total_start
        logger.info(f"[性能] 总耗时: {total_time:.2f}s | STT: {timings['stt']:.2f}s | LLM: {timings['llm']:.2f}s | TTS: {timings['tts']:.2f}s")
        
        return ""  # 处理完成，清空 buffer

    except Exception as e:
        logger.error(f"处理音频错误: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "message": str(e)})
        return partial_transcript  # 出错时保留 buffer，防止数据丢失


async def stream_tts(websocket: WebSocket, tts_service, text: str):
    """流式 TTS"""
    try:
        audio_data = await tts_service._text_to_speech_async(
            text=text,
            voice=getattr(settings, 'tts_default_voice', 'alloy')
        )
        
        chunk_size = 8 * 1024
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            await websocket.send_json({
                "type": "audio_chunk",
                "data": base64.b64encode(chunk).decode()
            })
            await asyncio.sleep(0.005)
        
        await websocket.send_json({"type": "audio_end"})
        
    except Exception as e:
        logger.error(f"TTS 错误: {e}")
