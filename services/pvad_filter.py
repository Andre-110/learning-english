"""
pVAD 音频过滤器

在音频送入 ASR 前，使用 pVAD 过滤背景噪音/他人声音。
- 未注册声纹时：pVAD 退化为普通 VAD（语音 vs 非语音）
- 已注册声纹时：只保留匹配用户声纹的音频

使用方式：
    filter_fn = get_pvad_filter()
    for chunk in audio_chunks:
        filtered = filter_fn(chunk)  # 返回应送入 ASR 的 bytes，可能为空
        if filtered:
            await asr.send_audio(filtered)
"""

import struct
from typing import Optional, Callable

from services.utils.logger import get_logger

logger = get_logger("services.pvad_filter")

# pVAD 帧大小：160 samples = 10ms @ 16kHz = 320 bytes
PVAD_FRAME_SAMPLES = 160
PVAD_FRAME_BYTES = PVAD_FRAME_SAMPLES * 2  # Int16


def _create_pvad_filter(threshold: float = 0.5) -> Optional[Callable[[bytes], bytes]]:
    """
    创建 pVAD 过滤函数。
    若 pVAD 不可用，返回 None（调用方应原样转发音频）。
    """
    try:
        import numpy as np
        from services.pvad import PersonalizedVAD

        pvad = PersonalizedVAD.get_instance(threshold=threshold)
        if not pvad._ensure_initialized():
            logger.warning("[pVAD] 初始化失败，跳过过滤")
            return None

        buffer = bytearray()

        def filter_fn(pcm_bytes: bytes) -> bytes:
            if not pcm_bytes:
                return b""
            buffer.extend(pcm_bytes)
            out = bytearray()
            while len(buffer) >= PVAD_FRAME_BYTES:
                frame_bytes = bytes(buffer[:PVAD_FRAME_BYTES])
                del buffer[:PVAD_FRAME_BYTES]
                # Int16 -> float32 [-1, 1]
                samples = struct.unpack(f"<{PVAD_FRAME_SAMPLES}h", frame_bytes)
                frame_np = (np.array(samples, dtype=np.float32) / 32768.0).reshape(PVAD_FRAME_SAMPLES)
                prob = pvad.detect(frame_np)
                if prob > threshold:
                    out.extend(frame_bytes)
            return bytes(out)

        logger.info("[pVAD] 过滤器已启用（通用 VAD 模式）")
        return filter_fn

    except Exception as e:
        logger.warning(f"[pVAD] 无法加载 pVAD，将直通音频: {e}")
        return None


def get_pvad_filter(use_pvad: bool = True, threshold: float = 0.5) -> Callable[[bytes], bytes]:
    """
    获取 pVAD 过滤函数。
    若 use_pvad=False 或 pVAD 不可用，返回直通函数（原样返回输入）。
    每个连接应调用一次，确保各会话有独立缓冲区。
    """
    if not use_pvad:
        return lambda x: x
    fn = _create_pvad_filter(threshold)
    return fn if fn else (lambda x: x)
