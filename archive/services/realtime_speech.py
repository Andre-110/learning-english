"""
实时语音输入服务 - 集成实时录音和VAD检测
参考: /home/ubuntu/ASR-LLM-TTS/13_SenceVoice_QWen2.5_edgeTTS_realTime.py
"""
import pyaudio
import wave
import threading
import numpy as np
import time
from queue import Queue
from typing import Optional, Callable, BinaryIO
import io
import webrtcvad
from services.speech import SpeechService, WhisperService
from services.utils.logger import get_logger

logger = get_logger("services.realtime_speech")


class RealtimeSpeechRecorder:
    """实时语音录制器 - 支持VAD检测和自动分段"""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        vad_mode: int = 3,
        no_speech_threshold: float = 1.0,
        vad_activation_rate: float = 0.4,
        vad_chunk_duration: float = 0.5
    ):
        """
        初始化实时语音录制器
        
        Args:
            sample_rate: 采样率（默认16000Hz）
            channels: 声道数（默认1，单声道）
            chunk_size: 音频块大小
            vad_mode: VAD模式（0-3，数字越大越敏感）
            no_speech_threshold: 无语音阈值（秒），超过此时间后触发保存
            vad_activation_rate: VAD激活率阈值（0-1），超过此比例认为有语音
            vad_chunk_duration: VAD检测时间窗口（秒）
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.no_speech_threshold = no_speech_threshold
        self.vad_activation_rate = vad_activation_rate
        self.vad_chunk_duration = vad_chunk_duration
        
        # 初始化WebRTC VAD
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(vad_mode)
        
        # 音频缓冲区
        self.audio_buffer = []
        self.segments_to_save = []
        self.last_active_time = time.time()
        self.last_vad_end_time = 0
        
        # 控制标志
        self.recording_active = False
        self.audio_stream = None
        self.pyaudio_instance = None
        
        # 回调函数
        self.on_speech_segment: Optional[Callable[[bytes], None]] = None
        
    def start_recording(self, on_speech_segment: Optional[Callable[[bytes], None]] = None):
        """
        开始录音
        
        Args:
            on_speech_segment: 当检测到语音段时的回调函数，接收音频数据(bytes)
        """
        if self.recording_active:
            logger.warning("录音已在运行中")
            return
        
        self.on_speech_segment = on_speech_segment
        self.recording_active = True
        
        # 初始化PyAudio
        self.pyaudio_instance = pyaudio.PyAudio()
        self.audio_stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        
        # 启动录音线程
        self.recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self.recording_thread.start()
        
        logger.info("实时语音录制已启动")
    
    def stop_recording(self):
        """停止录音"""
        if not self.recording_active:
            return
        
        self.recording_active = False
        
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
        
        if hasattr(self, 'recording_thread'):
            self.recording_thread.join(timeout=2.0)
        
        logger.info("实时语音录制已停止")
    
    def _recording_loop(self):
        """录音循环"""
        while self.recording_active:
            try:
                data = self.audio_stream.read(self.chunk_size, exception_on_overflow=False)
                self.audio_buffer.append(data)
                
                # 每0.5秒检测一次VAD
                buffer_duration = len(self.audio_buffer) * self.chunk_size / self.sample_rate
                if buffer_duration >= self.vad_chunk_duration:
                    # 拼接音频数据并检测VAD
                    raw_audio = b''.join(self.audio_buffer)
                    vad_result = self._check_vad_activity(raw_audio)
                    
                    if vad_result:
                        logger.debug("检测到语音活动")
                        self.last_active_time = time.time()
                        self.segments_to_save.append((raw_audio, time.time()))
                    else:
                        logger.debug("静音中...")
                    
                    self.audio_buffer = []  # 清空缓冲区
                
                # 检查是否需要保存（超过无语音阈值）
                if time.time() - self.last_active_time > self.no_speech_threshold:
                    if self.segments_to_save and self.segments_to_save[-1][1] > self.last_vad_end_time:
                        self._save_audio_segment()
                        self.last_active_time = time.time()
            
            except Exception as e:
                logger.error(f"录音循环错误: {e}")
                break
    
    def _check_vad_activity(self, audio_data: bytes) -> bool:
        """
        检测VAD活动
        
        Args:
            audio_data: 音频数据（bytes）
            
        Returns:
            True表示检测到语音活动
        """
        num_active = 0
        step = int(self.sample_rate * 0.02)  # 20ms块大小
        flag_rate = round(self.vad_activation_rate * len(audio_data) // step)
        
        for i in range(0, len(audio_data), step):
            chunk = audio_data[i:i + step]
            if len(chunk) == step:
                if self.vad.is_speech(chunk, sample_rate=self.sample_rate):
                    num_active += 1
        
        return num_active > flag_rate
    
    def _save_audio_segment(self):
        """保存音频段并触发回调"""
        if not self.segments_to_save:
            return
        
        # 获取有效段的时间范围
        start_time = self.segments_to_save[0][1]
        end_time = self.segments_to_save[-1][1]
        
        # 检查是否与之前的片段重叠
        if self.last_vad_end_time >= start_time:
            logger.debug("当前片段与之前片段重叠，跳过保存")
            self.segments_to_save.clear()
            return
        
        # 合并所有音频段
        audio_frames = [seg[0] for seg in self.segments_to_save]
        combined_audio = b''.join(audio_frames)
        
        # 记录保存的区间
        self.last_vad_end_time = end_time
        
        # 触发回调
        if self.on_speech_segment:
            try:
                self.on_speech_segment(combined_audio)
            except Exception as e:
                logger.error(f"语音段回调错误: {e}")
        
        # 清空缓冲区
        self.segments_to_save.clear()
    
    def get_current_audio(self) -> Optional[bytes]:
        """
        获取当前缓冲的音频数据
        
        Returns:
            音频数据（bytes），如果没有则返回None
        """
        if not self.segments_to_save:
            return None
        
        audio_frames = [seg[0] for seg in self.segments_to_save]
        return b''.join(audio_frames)


class RealtimeSpeechService:
    """实时语音服务 - 集成录音、VAD和ASR"""
    
    def __init__(
        self,
        speech_service: Optional[SpeechService] = None,
        sample_rate: int = 16000,
        **recorder_kwargs
    ):
        """
        初始化实时语音服务
        
        Args:
            speech_service: 语音转文本服务（默认使用WhisperService）
            sample_rate: 采样率
            **recorder_kwargs: 传递给RealtimeSpeechRecorder的其他参数
        """
        self.speech_service = speech_service or WhisperService()
        self.sample_rate = sample_rate
        
        # 创建录音器
        self.recorder = RealtimeSpeechRecorder(
            sample_rate=sample_rate,
            **recorder_kwargs
        )
        
        # 音频段队列
        self.audio_queue = Queue()
        
        # 回调函数
        self.on_transcription: Optional[Callable[[str], None]] = None
    
    def start_listening(self, on_transcription: Optional[Callable[[str], None]] = None):
        """
        开始监听语音输入
        
        Args:
            on_transcription: 当获得转录文本时的回调函数，接收文本(str)
        """
        self.on_transcription = on_transcription
        
        # 设置语音段回调
        self.recorder.start_recording(on_speech_segment=self._process_speech_segment)
        
        logger.info("实时语音监听已启动")
    
    def stop_listening(self):
        """停止监听"""
        self.recorder.stop_recording()
        logger.info("实时语音监听已停止")
    
    def _process_speech_segment(self, audio_data: bytes):
        """
        处理语音段
        
        Args:
            audio_data: 音频数据（bytes）
        """
        try:
            # 将音频数据转换为文件对象
            audio_file = self._bytes_to_wav_file(audio_data)
            
            # 调用ASR服务
            transcription = self.speech_service.transcribe_audio(audio_file)
            
            if transcription and transcription.strip():
                logger.info(f"转录结果: {transcription}")
                
                # 触发回调
                if self.on_transcription:
                    self.on_transcription(transcription.strip())
            else:
                logger.warning("转录结果为空")
        
        except Exception as e:
            logger.error(f"处理语音段错误: {e}")
    
    def _bytes_to_wav_file(self, audio_data: bytes) -> BinaryIO:
        """
        将PCM音频数据转换为WAV格式的文件对象
        
        Args:
            audio_data: PCM音频数据（bytes）
            
        Returns:
            WAV格式的文件对象
        """
        # 创建WAV文件
        wav_buffer = io.BytesIO()
        
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.recorder.channels)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data)
        
        wav_buffer.seek(0)
        return wav_buffer
    
    def record_and_transcribe(
        self,
        duration: float = 5.0,
        on_transcription: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        录制指定时长的音频并转录
        
        Args:
            duration: 录制时长（秒）
            on_transcription: 转录完成后的回调函数
            
        Returns:
            转录的文本
        """
        result_queue = Queue()
        
        def transcription_callback(text: str):
            result_queue.put(text)
        
        # 开始监听
        self.start_listening(on_transcription=transcription_callback)
        
        # 等待指定时长
        time.sleep(duration)
        
        # 停止监听
        self.stop_listening()
        
        # 获取结果
        try:
            result = result_queue.get(timeout=1.0)
            if on_transcription:
                on_transcription(result)
            return result
        except:
            return ""


# 便捷函数
def create_realtime_speech_service(**kwargs) -> RealtimeSpeechService:
    """创建实时语音服务实例"""
    return RealtimeSpeechService(**kwargs)


