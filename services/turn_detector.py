"""
Turn Detector 服务 - 基于 BERT 模型判断用户是否说完

借鉴自 FireRedChat 的 fireredchat-turn-detector 插件。

原理：
- 传统方法用"静音超时"判断用户说完（通常 1-2 秒）
- Turn Detector 用 BERT 模型进行语义判断（可缩短到 0.3 秒）

模型：
- 来源：FireRedTeam/FireRedChat-turn-detector
- 类型：ONNX 量化模型（CPU 运行）
- 支持：中文、英文、多语言
"""
import os
import re
import time
from typing import Optional
import numpy as np

from services.utils.logger import get_logger

logger = get_logger("services.turn_detector")

# 模型路径
MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "../proj/FireRedChat/agents/fireredchat-plugins/"
    "livekit-plugins-fireredchat-turn-detector/livekit/plugins/"
    "fireredchat_turn_detector/pretrained_models"
)

# 全局单例
_detector_instance: Optional["TurnDetector"] = None


class TurnDetector:
    """
    Turn Detector - 判断用户是否说完
    
    使用 BERT 模型进行语义判断，比静音超时更准确。
    
    用法：
        detector = TurnDetector.get_instance()
        
        # 判断是否说完
        if detector.is_turn_complete("I want to"):
            print("用户说完了")
        
        # 获取概率（用于调参）
        prob = detector.get_probability("I want to")  # → 0.39
    """
    
    def __init__(
        self,
        model_type: str = "multilingual",
        threshold: float = 0.5,
        model_dir: Optional[str] = None
    ):
        """
        初始化 Turn Detector
        
        Args:
            model_type: 模型类型 ("chinese" 或 "multilingual")
            threshold: 判断阈值（默认 0.5）
            model_dir: 模型目录路径
        """
        self.threshold = threshold
        self.model_type = model_type
        self.model_dir = model_dir or MODEL_DIR
        
        self._session = None
        self._tokenizer = None
        self._initialized = False
        
    def _ensure_initialized(self) -> bool:
        """确保模型已加载"""
        if self._initialized:
            return True
        
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer
            
            # 加载 tokenizer
            tokenizer_path = os.path.join(self.model_dir, "tokenizer")
            if not os.path.exists(tokenizer_path):
                logger.error(f"Tokenizer 不存在: {tokenizer_path}")
                return False
            
            self._tokenizer = AutoTokenizer.from_pretrained(
                tokenizer_path,
                local_files_only=True,
                truncation_side="left"
            )
            
            # 加载 ONNX 模型
            if self.model_type == "chinese":
                model_path = os.path.join(self.model_dir, "chinese_best_model_q8.onnx")
            else:
                model_path = os.path.join(self.model_dir, "multilingual_best_model_q8.onnx")
            
            if not os.path.exists(model_path):
                logger.error(f"模型文件不存在: {model_path}")
                return False
            
            self._session = ort.InferenceSession(
                model_path,
                providers=["CPUExecutionProvider"]
            )
            
            self._initialized = True
            logger.info(f"Turn Detector 初始化成功: type={self.model_type}, threshold={self.threshold}")
            return True
            
        except Exception as e:
            logger.error(f"Turn Detector 初始化失败: {e}")
            return False
    
    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Softmax 函数"""
        exp_x = np.exp(x - np.max(x, axis=1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=1, keepdims=True)
    
    def _preprocess_text(self, text: str) -> str:
        """预处理文本（移除标点）"""
        # 移除标点符号，只保留语义内容
        return re.sub(r"[，。？！,.\s?!]", "", text)
    
    def get_probability(self, text: str) -> float:
        """
        获取 End of Utterance 概率
        
        Args:
            text: 用户说的话
            
        Returns:
            概率值 (0-1)，越高表示越可能说完了
        """
        if not self._ensure_initialized():
            logger.warning("Turn Detector 未初始化，返回默认值 0.5")
            return 0.5
        
        try:
            start_time = time.time()
            
            # 预处理
            processed_text = self._preprocess_text(text)
            if not processed_text:
                return 0.5
            
            # Tokenize
            inputs = self._tokenizer(
                processed_text,
                truncation=True,
                padding='max_length',
                add_special_tokens=False,
                return_tensors="np",
                max_length=128,
            )
            
            # 推理
            outputs = self._session.run(None, {
                "input_ids": inputs["input_ids"].astype("int64"),
                "attention_mask": inputs["attention_mask"].astype("int64")
            })
            
            # Softmax
            prob = float(self._softmax(outputs[0]).flatten()[-1])
            
            elapsed = time.time() - start_time
            logger.debug(f"Turn Detector: '{text[:30]}...' → {prob:.2%} ({elapsed*1000:.1f}ms)")
            
            return prob
            
        except Exception as e:
            logger.error(f"Turn Detector 推理失败: {e}")
            return 0.5
    
    def is_turn_complete(self, text: str) -> bool:
        """
        判断用户是否说完
        
        Args:
            text: 用户说的话
            
        Returns:
            True 如果用户说完了
        """
        prob = self.get_probability(text)
        return prob > self.threshold
    
    @classmethod
    def get_instance(
        cls,
        model_type: str = "multilingual",
        threshold: float = 0.5
    ) -> "TurnDetector":
        """
        获取单例实例
        
        Args:
            model_type: 模型类型
            threshold: 判断阈值
        """
        global _detector_instance
        
        if _detector_instance is None:
            _detector_instance = cls(model_type=model_type, threshold=threshold)
        
        return _detector_instance


# 便捷函数
def is_turn_complete(text: str, threshold: float = 0.5) -> bool:
    """
    判断用户是否说完（便捷函数）
    
    Args:
        text: 用户说的话
        threshold: 判断阈值
        
    Returns:
        True 如果用户说完了
    """
    detector = TurnDetector.get_instance(threshold=threshold)
    return detector.is_turn_complete(text)


def get_eou_probability(text: str) -> float:
    """
    获取 End of Utterance 概率（便捷函数）
    
    Args:
        text: 用户说的话
        
    Returns:
        概率值 (0-1)
    """
    detector = TurnDetector.get_instance()
    return detector.get_probability(text)
