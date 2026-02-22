"""
pVAD (Personalized Voice Activity Detection) 服务

借鉴自 FireRedChat 的 fireredchat-pvad 插件。

功能：
1. 区分谁在说话（用户 vs AI / 背景噪音）
2. 更精确的语音活动检测
3. 说话人验证（Voice Print）

原理：
- ECAPA-TDNN 提取说话人嵌入向量（192维）
- pVAD ONNX 模型结合声纹进行检测
- 只有匹配注册声纹的声音才被识别为"用户说话"

使用场景：
- 过滤背景杂音（电视、他人交谈）
- 避免 AI 播放的声音被误识别
- 多人场景识别特定用户
"""
import os
import time
from typing import Optional, Tuple
import numpy as np

from services.utils.logger import get_logger

logger = get_logger("services.pvad")

# 模型路径
MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "../proj/FireRedChat/agents/fireredchat-plugins/"
    "livekit-plugins-fireredchat-pvad/livekit/plugins/"
    "fireredchat_pvad/resources"
)

# 全局单例
_pvad_instance: Optional["PersonalizedVAD"] = None


class SpeakerEmbeddingExtractor:
    """
    说话人嵌入提取器
    
    使用 ECAPA-TDNN 模型提取 192 维说话人嵌入向量。
    """
    
    def __init__(self, model_dir: Optional[str] = None, device: str = "cpu"):
        self.model_dir = model_dir or os.path.join(MODEL_DIR, "spkrec-ecapa-voxceleb")
        self.device = device
        self._classifier = None
        self._initialized = False
    
    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True
        
        try:
            from speechbrain.inference.speaker import EncoderClassifier
            
            if not os.path.exists(self.model_dir):
                logger.error(f"ECAPA-TDNN 模型不存在: {self.model_dir}")
                return False
            
            device_str = "cpu" if self.device == "cpu" else f"cuda:{self.device}"
            self._classifier = EncoderClassifier.from_hparams(
                source=self.model_dir,
                savedir=self.model_dir,
                run_opts={"device": device_str}
            )
            
            self._initialized = True
            logger.info("SpeakerEmbeddingExtractor 初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"SpeakerEmbeddingExtractor 初始化失败: {e}")
            return False
    
    def extract(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """
        提取说话人嵌入
        
        Args:
            audio: 音频数据 (16kHz, float32, -1 to 1)
            
        Returns:
            192 维嵌入向量，失败返回 None
        """
        if not self._ensure_initialized():
            return None
        
        try:
            import torch
            
            # 转换为 tensor
            if isinstance(audio, np.ndarray):
                audio_tensor = torch.tensor(audio, dtype=torch.float32)
            else:
                audio_tensor = audio
            
            # 提取嵌入
            embeddings = self._classifier.encode_batch(audio_tensor)[0][0].detach()
            embeddings = embeddings / embeddings.norm(p=2, dim=0, keepdim=True)
            embeddings = embeddings.cpu().unsqueeze(0).numpy()
            
            return embeddings
            
        except Exception as e:
            logger.error(f"嵌入提取失败: {e}")
            return None


class PersonalizedVAD:
    """
    个性化语音活动检测器
    
    使用声纹识别来区分谁在说话。
    
    使用流程：
        1. 初始化时或首次说话时注册用户声纹
        2. 后续检测时对比声纹
        3. 只有匹配的声音才返回高概率
    
    用法：
        pvad = PersonalizedVAD.get_instance()
        
        # 注册用户声纹（用一段用户音频）
        pvad.register_speaker(user_audio)
        
        # 检测音频帧
        prob = pvad.detect(audio_frame)  # 0-1
        if prob > 0.5:
            print("用户在说话")
    """
    
    SAMPLE_RATE = 16000
    FRAME_SIZE = 160  # 10ms @ 16kHz
    
    def __init__(self, model_dir: Optional[str] = None, threshold: float = 0.5):
        self.model_dir = model_dir or MODEL_DIR
        self.threshold = threshold
        
        self._session = None
        self._spk_extractor: Optional[SpeakerEmbeddingExtractor] = None
        self._initialized = False
        
        # 缓冲区
        self._mel_buffer = None
        self._gru_buffer = None
        self._speaker_embedding = None
        
    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True
        
        try:
            import onnxruntime as ort
            
            # 加载 ONNX 模型
            onnx_path = os.path.join(self.model_dir, "pvad.onnx")
            if not os.path.exists(onnx_path):
                logger.error(f"pVAD 模型不存在: {onnx_path}")
                return False
            
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 4
            opts.intra_op_num_threads = 4
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            
            self._session = ort.InferenceSession(
                onnx_path,
                providers=["CPUExecutionProvider"],
                sess_options=opts
            )
            
            # 初始化说话人嵌入提取器
            self._spk_extractor = SpeakerEmbeddingExtractor(
                model_dir=os.path.join(self.model_dir, "spkrec-ecapa-voxceleb")
            )
            
            # 初始化缓冲区
            self.reset()
            
            self._initialized = True
            logger.info("PersonalizedVAD 初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"PersonalizedVAD 初始化失败: {e}")
            return False
    
    def reset(self):
        """重置内部状态"""
        self._mel_buffer = np.zeros((1, 80, 15), dtype=np.float32)
        self._gru_buffer = np.zeros((2, 1, 256), dtype=np.float32)
    
    def register_speaker(self, audio: np.ndarray) -> bool:
        """
        注册用户声纹
        
        Args:
            audio: 用户音频样本 (16kHz, float32, 建议 2-5 秒)
            
        Returns:
            是否注册成功
        """
        if not self._ensure_initialized():
            return False
        
        try:
            # 提取嵌入
            embedding = self._spk_extractor.extract(audio)
            if embedding is None:
                return False
            
            self._speaker_embedding = embedding.astype(np.float32)
            logger.info(f"声纹注册成功，嵌入维度: {self._speaker_embedding.shape}")
            return True
            
        except Exception as e:
            logger.error(f"声纹注册失败: {e}")
            return False
    
    def detect(self, audio_frame: np.ndarray) -> float:
        """
        检测音频帧是否为目标用户说话
        
        Args:
            audio_frame: 音频帧 (160 samples = 10ms @ 16kHz)
            
        Returns:
            概率值 (0-1)，未注册声纹时返回普通 VAD 结果
        """
        if not self._ensure_initialized():
            return 0.0
        
        try:
            # 确保帧大小正确
            if audio_frame.shape[0] != self.FRAME_SIZE:
                logger.debug(f"帧大小错误: {audio_frame.shape[0]}, 需要 {self.FRAME_SIZE}")
                return 0.0
            
            wav_np = audio_frame.reshape((1, self.FRAME_SIZE)).astype(np.float32)
            
            # 如果没有注册声纹，使用零向量（普通 VAD）
            spk_emb = self._speaker_embedding if self._speaker_embedding is not None else np.zeros((1, 192), dtype=np.float32)
            
            # 推理
            outputs = self._session.run(None, {
                'input_audio': wav_np,
                'spkemb': spk_emb,
                'mel_buffer': self._mel_buffer,
                'gru_buffer': self._gru_buffer
            })
            
            # 更新缓冲区
            raw_prob = float(outputs[1][0].tolist()[0])
            self._mel_buffer = outputs[2]
            self._gru_buffer = outputs[3]
            
            return raw_prob
            
        except Exception as e:
            logger.error(f"pVAD 检测失败: {e}")
            return 0.0
    
    def is_user_speaking(self, audio_frame: np.ndarray) -> bool:
        """
        判断是否是用户在说话
        
        Args:
            audio_frame: 音频帧
            
        Returns:
            True 如果是用户在说话
        """
        prob = self.detect(audio_frame)
        return prob > self.threshold
    
    @property
    def has_registered_speaker(self) -> bool:
        """是否已注册说话人"""
        return self._speaker_embedding is not None
    
    @classmethod
    def get_instance(cls, threshold: float = 0.5) -> "PersonalizedVAD":
        """获取单例实例"""
        global _pvad_instance
        
        if _pvad_instance is None:
            _pvad_instance = cls(threshold=threshold)
        
        return _pvad_instance


# 便捷函数
def register_user_voice(audio: np.ndarray) -> bool:
    """注册用户声纹"""
    pvad = PersonalizedVAD.get_instance()
    return pvad.register_speaker(audio)


def is_user_speaking(audio_frame: np.ndarray) -> bool:
    """判断是否是用户在说话"""
    pvad = PersonalizedVAD.get_instance()
    return pvad.is_user_speaking(audio_frame)
