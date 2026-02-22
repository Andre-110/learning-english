"""
语音服务预热 - 在服务启动时预加载模型
"""
from services.speech import SpeechServiceFactory
from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("services.speech_warmup")

# 全局单例：预热后的语音服务（供其他模块复用）
_warmed_speech_service = None


def get_warmed_speech_service():
    """获取预热后的语音服务单例"""
    global _warmed_speech_service
    return _warmed_speech_service


def warmup_speech_service():
    """预热语音服务（预加载模型）"""
    global _warmed_speech_service
    
    try:
        logger.info("开始预热语音服务...")
        settings = Settings()
        
        if settings.speech_provider == "funasr":
            logger.info("预热FunASR服务（这可能需要20-30秒）...")
            speech_service = SpeechServiceFactory.create(
                provider="funasr",
                model_dir=settings.funasr_model_dir,
                model_name=settings.funasr_model_name,
                language=settings.funasr_language
            )
            # 触发模型加载（使用一个小的测试音频）
            # FunASR使用延迟加载，需要调用transcribe_audio才会加载模型
            try:
                import io
                import wave
                # 创建一个最小的WAV文件（1秒静音，16kHz，单声道）
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b'\x00' * 16000)  # 1秒的静音
                wav_buffer.seek(0)
                
                # 触发模型加载（即使转录失败也没关系，主要是加载模型）
                try:
                    speech_service.transcribe_audio(wav_buffer)
                except:
                    pass  # 忽略转录错误，只要模型加载了就行
                
                logger.info("✓ FunASR服务预热完成（模型已加载）")
            except Exception as e:
                logger.warning(f"FunASR预热测试失败（模型可能仍会延迟加载）: {e}")
        else:
            logger.info("预热Whisper服务...")
            speech_service = SpeechServiceFactory.create(provider="whisper")
            logger.info("✓ Whisper服务预热完成")
        
        # 保存为全局单例
        _warmed_speech_service = speech_service
        
        logger.info("语音服务预热成功（已保存为全局单例）")
        
        # 🆕 预热 Turn Detector (BERT 模型)
        _warmup_turn_detector()
        
        return speech_service
    except Exception as e:
        logger.error(f"语音服务预热失败: {e}", exc_info=True)
        return None


def _warmup_turn_detector():
    """预热 Turn Detector (BERT ONNX 模型)"""
    try:
        import time
        logger.info("预热 Turn Detector (BERT 模型)...")
        start = time.time()
        
        from services.turn_detector import TurnDetector
        detector = TurnDetector.get_instance()
        
        # 触发模型加载
        prob = detector.get_probability("Hello, how are you?")
        
        elapsed = time.time() - start
        logger.info(f"✓ Turn Detector 预热完成 ({elapsed:.2f}s)")
    except Exception as e:
        logger.warning(f"Turn Detector 预热失败（将在首次使用时加载）: {e}")

