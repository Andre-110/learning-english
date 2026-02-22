"""
FunASR本地部署语音服务 - 使用FunASR/SenseVoice进行本地语音识别
参考: /home/ubuntu/ASR-LLM-TTS/
"""
from typing import Optional, BinaryIO
import os
import tempfile
from services.speech import SpeechService
from services.utils.logger import get_logger

logger = get_logger("services.funasr")


class FunASRService(SpeechService):
    """使用FunASR/SenseVoice的本地语音服务"""
    
    def __init__(
        self,
        model_dir: Optional[str] = None,
        model_name: str = "iic/SenseVoiceSmall",
        language: str = "auto",
        use_itn: bool = False,
        trust_remote_code: bool = True
    ):
        """
        初始化FunASR服务
        
        Args:
            model_dir: 本地模型目录路径（如果已下载）
            model_name: 模型名称（ModelScope或HuggingFace）
            language: 语言代码（"auto", "zh", "en", "yue", "ja", "ko", "nospeech"）
            use_itn: 是否使用逆文本规范化
            trust_remote_code: 是否信任远程代码
        """
        self.model_dir = model_dir
        self.model_name = model_name
        self.language = language
        self.use_itn = use_itn
        self.trust_remote_code = trust_remote_code
        
        # 延迟加载模型（避免启动时加载）
        self._model = None
        
        logger.info(f"FunASR服务初始化: model={model_name}, language={language}")
    
    def _load_model(self):
        """延迟加载模型"""
        if self._model is not None:
            return self._model
        
        try:
            from funasr import AutoModel
            
            # 使用本地模型目录或模型名称
            model_path = self.model_dir or self.model_name
            
            logger.info(f"正在加载FunASR模型: {model_path}")
            
            # 优化模型加载参数，禁用更新检查以加快加载速度
            self._model = AutoModel(
                model=model_path,
                trust_remote_code=self.trust_remote_code,
                disable_update=True,  # 禁用更新检查，加快加载速度
            )
            
            logger.info("FunASR模型加载成功")
            return self._model
        
        except ImportError:
            raise ImportError(
                "FunASR未安装。请运行: pip install funasr"
            )
        except Exception as e:
            logger.error(f"加载FunASR模型失败: {e}")
            raise Exception(f"加载FunASR模型失败: {e}")
    
    def transcribe_audio(
        self,
        audio_file: BinaryIO,
        language: Optional[str] = None
    ) -> str:
        """
        使用FunASR转录音频
        
        Args:
            audio_file: 音频文件对象
            language: 可选，指定语言代码（覆盖初始化时的设置）
            
        Returns:
            转录的文本
        """
        try:
            # 加载模型（如果尚未加载）
            model = self._load_model()
            
            # 使用传入的language或默认的language
            detect_language = language or self.language
            
            # 将音频文件保存到临时文件（FunASR需要文件路径）
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                tmp_path = tmp_file.name
                audio_file.seek(0)
                tmp_file.write(audio_file.read())
            
            try:
                # 调用FunASR进行转录
                logger.debug(f"开始转录: {tmp_path}, language={detect_language}")
                
                res = model.generate(
                    input=tmp_path,
                    cache={},
                    language=detect_language,
                    use_itn=self.use_itn,
                )
                
                # 解析结果
                if res and len(res) > 0:
                    # FunASR返回格式: [{'text': '...', ...}]
                    text = res[0].get('text', '')
                    
                    # 如果text包含">"，提取">"之后的内容（SenseVoice格式）
                    if '>' in text:
                        text = text.split('>')[-1]
                    
                    logger.info(f"转录成功: {text[:100]}...")
                    return text.strip()
                else:
                    logger.warning("FunASR返回空结果")
                    return ""
            
            finally:
                # 清理临时文件
                try:
                    os.unlink(tmp_path)
                except:
                    pass
        
        except Exception as e:
            logger.error(f"FunASR转录失败: {e}")
            raise Exception(f"FunASR转录失败: {e}")


