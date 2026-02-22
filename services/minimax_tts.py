"""
MiniMax TTS 语音合成服务

使用 MiniMax WebSocket API 进行高质量中文语音合成。
API: wss://api.minimaxi.com/ws/v1/t2a_v2

优势：
- 高质量中文语音：多种音色，自然流畅
- 低延迟：WebSocket 流式传输
- 多音色支持：精英青年、少女、御姐等

参考：UserGenie.ai 项目的 minimax-provider.ts
"""
import asyncio
import json
from typing import Optional, List, Dict
from dataclasses import dataclass

import websockets

from services.tts import TTSService
from services.utils.logger import get_logger

logger = get_logger("services.minimax_tts")


@dataclass 
class MiniMaxTTSConfig:
    """MiniMax TTS 配置"""
    
    # API 配置
    api_key: str = ""
    
    # 端点
    endpoint: str = "wss://api.minimaxi.com/ws/v1/t2a_v2"
    
    # 模型配置
    model: str = "speech-2.6-hd"  # speech-2.6-hd 或 speech-2.6
    
    # 音频配置
    sample_rate: int = 32000  # MiniMax 输出 32kHz
    bitrate: int = 128000
    audio_format: str = "pcm"
    channels: int = 1
    
    # 语音配置
    default_voice: str = "male-qn-jingying"  # 精英青年音色
    speed: float = 1.0  # 语速 0.5-2.0
    volume: float = 1.0  # 音量
    pitch: int = 0  # 音调
    
    # 超时配置
    timeout: float = 60.0
    
    def __post_init__(self):
        import os
        if not self.api_key:
            self.api_key = os.getenv("MINIMAX_API_KEY", "")


# MiniMax 支持的音色列表
MINIMAX_VOICES = {
    # 青年音色
    "male-qn-qingse": "青涩青年音色",
    "male-qn-jingying": "精英青年音色",
    "male-qn-badao": "霸道青年音色",
    "male-qn-daxuesheng": "青年大学生音色",
    
    # 女性音色
    "female-shaonv": "少女音色",
    "female-yujie": "御姐音色",
    "female-chengshu": "成熟女性音色",
    "female-tianmei": "甜美女性音色",
    
    # 主持人音色
    "presenter_male": "男性主持人",
    "presenter_female": "女性主持人",
    
    # 有声书音色
    "audiobook_male_1": "男性有声书1",
    "audiobook_male_2": "男性有声书2",
    "audiobook_female_1": "女性有声书1",
    "audiobook_female_2": "女性有声书2",
    
    # 精品音色（更高质量）
    "male-qn-qingse-jingpin": "青涩青年音色-精品",
    "male-qn-jingying-jingpin": "精英青年音色-精品",
    "female-shaonv-jingpin": "少女音色-精品",
    "female-yujie-jingpin": "御姐音色-精品",
    "female-chengshu-jingpin": "成熟女性音色-精品",
    "female-tianmei-jingpin": "甜美女性音色-精品",
}


class MiniMaxTTSService(TTSService):
    """
    MiniMax TTS 服务
    
    使用 WebSocket 流式接收音频数据。
    """
    
    def __init__(self, config: Optional[MiniMaxTTSConfig] = None):
        self.config = config or MiniMaxTTSConfig()
        
        if not self.config.api_key:
            raise ValueError(
                "MiniMax API Key 未配置，请设置环境变量 MINIMAX_API_KEY"
            )
        
        # 调试：打印 API Key 前缀确认正确加载
        key_prefix = self.config.api_key[:30] if len(self.config.api_key) > 30 else self.config.api_key
        logger.info(f"MiniMaxTTSService 初始化: model={self.config.model}, voice={self.config.default_voice}, key_prefix={key_prefix}...")
    
    async def _text_to_speech_async(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> bytes:
        """
        异步将文本转换为语音
        
        Args:
            text: 要转换的文本
            voice: 音色 ID
            rate: 语速（MiniMax 使用数值 0.5-2.0）
            volume: 音量（忽略，使用配置）
            pitch: 音调（忽略，使用配置）
        
        Returns:
            PCM 音频数据 (32kHz, 16-bit, mono)
        """
        voice = voice or self.config.default_voice
        
        # 验证音色
        if voice not in MINIMAX_VOICES:
            logger.warning(f"未知音色 {voice}，使用默认 {self.config.default_voice}")
            voice = self.config.default_voice
        
        # 解析语速
        speed = self.config.speed
        if rate:
            try:
                # 支持 "+50%" 或 "1.5" 格式
                if rate.endswith("%"):
                    percent = float(rate.rstrip("%").lstrip("+"))
                    speed = 1.0 + (percent / 100)
                else:
                    speed = float(rate)
                speed = max(0.5, min(2.0, speed))  # 限制范围
            except:
                pass
        
        logger.info(f"[MiniMax TTS] 合成: voice={voice}, speed={speed}x, text={text[:30]}...")
        
        try:
            audio_data = await self._synthesize_speech(text, voice, speed)
            logger.info(f"[MiniMax TTS] 生成 {len(audio_data)} bytes 音频")
            return audio_data
        except Exception as e:
            logger.error(f"[MiniMax TTS] 合成失败: {e}")
            raise
    
    async def _synthesize_speech(
        self,
        text: str,
        voice: str,
        speed: float
    ) -> bytes:
        """使用 WebSocket 合成语音"""
        audio_chunks = []
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}"
        }
        
        try:
            async with websockets.connect(
                self.config.endpoint,
                extra_headers=headers,
                close_timeout=5
            ) as ws:
                # 等待连接确认
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(response)
                
                if data.get("event") != "connected_success":
                    raise Exception(f"连接失败: {data}")
                
                logger.debug("[MiniMax TTS] WebSocket 连接成功")
                
                # 发送 task_start
                start_msg = {
                    "event": "task_start",
                    "model": self.config.model,
                    "voice_setting": {
                        "voice_id": voice,
                        "speed": speed,
                        "vol": self.config.volume,
                        "pitch": self.config.pitch,
                        "english_normalization": False
                    },
                    "audio_setting": {
                        "sample_rate": self.config.sample_rate,
                        "bitrate": self.config.bitrate,
                        "format": self.config.audio_format,
                        "channel": self.config.channels
                    }
                }
                await ws.send(json.dumps(start_msg))
                
                # 等待 task_started
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(response)
                
                if data.get("event") != "task_started":
                    raise Exception(f"启动任务失败: {data}")
                
                logger.debug("[MiniMax TTS] 任务已启动")
                
                # 发送文本
                continue_msg = {
                    "event": "task_continue",
                    "text": text
                }
                await ws.send(json.dumps(continue_msg))
                
                # 接收音频数据
                while True:
                    try:
                        response = await asyncio.wait_for(
                            ws.recv(),
                            timeout=self.config.timeout
                        )
                        data = json.loads(response)
                        
                        # 🔴 检查 base_resp 中的错误（如余额不足）
                        base_resp = data.get("base_resp", {})
                        if base_resp.get("status_code", 0) != 0:
                            error_msg = base_resp.get("status_msg", "unknown error")
                            logger.error(f"[MiniMax TTS] API 错误: code={base_resp.get('status_code')}, msg={error_msg}")
                            raise Exception(f"MiniMax API 错误: {error_msg} (code={base_resp.get('status_code')})")
                        
                        # 提取音频数据
                        if data.get("data") and data["data"].get("audio"):
                            audio_hex = data["data"]["audio"]
                            audio_bytes = bytes.fromhex(audio_hex)
                            audio_chunks.append(audio_bytes)
                        
                        # 检查是否完成
                        if data.get("is_final"):
                            logger.debug(f"[MiniMax TTS] 合成完成，共 {len(audio_chunks)} 个块")
                            break
                        
                        # 检查错误事件
                        if data.get("event") == "error" or data.get("error"):
                            error_msg = data.get("error", {}).get("message", str(data))
                            raise Exception(f"服务端错误: {error_msg}")
                    
                    except asyncio.TimeoutError:
                        logger.warning("[MiniMax TTS] 接收超时")
                        break
                
                # 发送结束消息
                try:
                    await ws.send(json.dumps({"event": "task_finish"}))
                except:
                    pass
        
        except websockets.exceptions.WebSocketException as e:
            raise Exception(f"WebSocket 错误: {e}")
        
        return b"".join(audio_chunks)
    
    async def synthesize_stream_async(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None
    ):
        """
        🚀 流式 TTS：边接收边 yield 音频块
        
        参考 UserGenie 的优化策略：
        - 每收到一个音频块就立即 yield，不等待完整音频
        - 前端可以更早开始播放
        - 带超时重试机制（5秒超时，最多3次重试）
        
        Yields:
            dict: {
                "audio_bytes": bytes,  # PCM 音频数据
                "chunk_index": int,    # 块索引
                "is_first": bool,      # 是否首块
                "is_last": bool,       # 是否末块
            }
        """
        voice = voice or self.config.default_voice
        speed = speed or self.config.speed
        
        # 验证音色
        if voice not in MINIMAX_VOICES:
            logger.warning(f"未知音色 {voice}，使用默认 {self.config.default_voice}")
            voice = self.config.default_voice
        
        logger.info(f"[MiniMax TTS Stream] 开始流式合成: voice={voice}, speed={speed}x, text={text[:30]}...")
        
        # 🔄 带超时重试（参考 UserGenie：5秒超时，最多3次）
        TTS_TIMEOUT_SECONDS = 5.0
        MAX_RETRIES = 3
        
        # 🆕 首块延迟计时
        import time
        stream_start_time = time.time()
        first_chunk_time = None
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}"
        }
        
        for attempt in range(1, MAX_RETRIES + 1):
            chunk_index = 0
            is_first = True
            
            try:
                async with websockets.connect(
                    self.config.endpoint,
                    extra_headers=headers,
                    close_timeout=5
                ) as ws:
                    # 等待连接确认
                    response = await asyncio.wait_for(ws.recv(), timeout=TTS_TIMEOUT_SECONDS)
                    data = json.loads(response)
                    
                    if data.get("event") != "connected_success":
                        raise Exception(f"连接失败: {data}")
                    
                    logger.debug(f"[MiniMax TTS Stream] Attempt {attempt}: WebSocket 连接成功")
                    
                    # 发送 task_start
                    start_msg = {
                        "event": "task_start",
                        "model": self.config.model,
                        "voice_setting": {
                            "voice_id": voice,
                            "speed": speed,
                            "vol": self.config.volume,
                            "pitch": self.config.pitch,
                            "english_normalization": False
                        },
                        "audio_setting": {
                            "sample_rate": self.config.sample_rate,
                            "bitrate": self.config.bitrate,
                            "format": self.config.audio_format,
                            "channel": self.config.channels
                        }
                    }
                    await ws.send(json.dumps(start_msg))
                    
                    # 等待 task_started
                    response = await asyncio.wait_for(ws.recv(), timeout=TTS_TIMEOUT_SECONDS)
                    data = json.loads(response)
                    
                    if data.get("event") != "task_started":
                        raise Exception(f"启动任务失败: {data}")
                    
                    # 发送文本
                    continue_msg = {
                        "event": "task_continue",
                        "text": text
                    }
                    await ws.send(json.dumps(continue_msg))
                    
                    # 🚀 流式接收音频数据，边收边 yield
                    while True:
                        try:
                            response = await asyncio.wait_for(
                                ws.recv(),
                                timeout=TTS_TIMEOUT_SECONDS
                            )
                            data = json.loads(response)
                            
                            # 🔴 检查 base_resp 中的错误（如余额不足）
                            base_resp = data.get("base_resp", {})
                            if base_resp.get("status_code", 0) != 0:
                                error_msg = base_resp.get("status_msg", "unknown error")
                                logger.error(f"[MiniMax TTS Stream] API 错误: code={base_resp.get('status_code')}, msg={error_msg}")
                                raise Exception(f"MiniMax API 错误: {error_msg} (code={base_resp.get('status_code')})")
                            
                            # 提取音频数据并立即 yield
                            if data.get("data") and data["data"].get("audio"):
                                audio_hex = data["data"]["audio"]
                                audio_bytes = bytes.fromhex(audio_hex)
                                is_last = data.get("is_final", False)
                                
                                yield {
                                    "audio_bytes": audio_bytes,
                                    "chunk_index": chunk_index,
                                    "is_first": is_first,
                                    "is_last": is_last,
                                }
                                
                                if is_first:
                                    first_chunk_time = time.time()
                                    first_chunk_latency_ms = (first_chunk_time - stream_start_time) * 1000
                                    logger.info(f"[MiniMax TTS Stream] 🚀 首块延迟: {first_chunk_latency_ms:.0f}ms, 大小: {len(audio_bytes)} bytes")
                                    is_first = False
                                chunk_index += 1
                            
                            # 检查是否完成
                            if data.get("is_final"):
                                logger.info(f"[MiniMax TTS Stream] 完成，共 {chunk_index} 块")
                                break
                            
                            # 检查错误事件
                            if data.get("event") == "error" or data.get("error"):
                                error_msg = data.get("error", {}).get("message", str(data))
                                raise Exception(f"服务端错误: {error_msg}")
                        
                        except asyncio.TimeoutError:
                            logger.warning(f"[MiniMax TTS Stream] Attempt {attempt}: 接收超时")
                            raise
                    
                    # 发送结束消息
                    try:
                        await ws.send(json.dumps({"event": "task_finish"}))
                    except:
                        pass
                    
                    # 成功完成，退出重试循环
                    return
            
            except Exception as e:
                logger.warning(f"[MiniMax TTS Stream] Attempt {attempt}/{MAX_RETRIES} 失败: {e}")
                if attempt < MAX_RETRIES:
                    logger.info(f"[MiniMax TTS Stream] 100ms 后重试...")
                    await asyncio.sleep(0.1)
                else:
                    logger.error(f"[MiniMax TTS Stream] 所有 {MAX_RETRIES} 次尝试均失败")
                    raise
    
    def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> bytes:
        """
        同步接口：将文本转换为语音
        
        Returns:
            PCM 音频数据 (32kHz, 16-bit, mono)
        """
        try:
            loop = asyncio.get_running_loop()
            raise RuntimeError("在异步环境中，请使用 _text_to_speech_async 方法")
        except RuntimeError as e:
            if "异步环境" in str(e):
                raise
        
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(
                self._text_to_speech_async(text, voice, rate, volume, pitch)
            )
        finally:
            loop.close()
    
    def list_voices(self, language: Optional[str] = None) -> List[Dict]:
        """
        列出可用的音色
        
        Args:
            language: 语言代码（MiniMax 主要支持中文）
        
        Returns:
            音色列表
        """
        voices = []
        for voice_id, voice_name in MINIMAX_VOICES.items():
            # 判断性别
            if voice_id.startswith("male") or voice_id.startswith("audiobook_male") or voice_id == "presenter_male":
                gender = "Male"
            elif voice_id.startswith("female") or voice_id.startswith("audiobook_female") or voice_id == "presenter_female":
                gender = "Female"
            else:
                gender = "Unknown"
            
            voices.append({
                "ShortName": voice_id,
                "Locale": "zh-CN",
                "Gender": gender,
                "FriendlyName": f"MiniMax {voice_name}",
                "Description": voice_name
            })
        
        return voices
    
    @staticmethod
    def get_sample_rate() -> int:
        """获取输出采样率"""
        return 32000  # MiniMax 输出 32kHz


# 工厂函数
def create_minimax_tts(config: Optional[MiniMaxTTSConfig] = None) -> MiniMaxTTSService:
    """创建 MiniMax TTS 服务实例"""
    return MiniMaxTTSService(config)
