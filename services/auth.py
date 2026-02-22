"""
用户认证服务 - 处理密码加密、JWT token生成和验证
"""
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional
from config.settings import Settings
from services.utils.logger import get_logger

logger = get_logger("services.auth")

settings = Settings()

# JWT配置（从环境变量读取，如果没有则使用默认值）
JWT_SECRET_KEY = getattr(settings, 'jwt_secret_key', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24  # Token过期时间（小时）


class AuthService:
    """认证服务"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        加密密码
        
        Args:
            password: 明文密码
            
        Returns:
            加密后的密码哈希值
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        验证密码
        
        Args:
            password: 明文密码
            password_hash: 密码哈希值
            
        Returns:
            是否匹配
        """
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                password_hash.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"密码验证失败: {e}")
            return False
    
    @staticmethod
    def generate_token(user_id: str, username: str) -> str:
        """
        生成JWT token
        
        Args:
            user_id: 用户ID
            username: 用户名
            
        Returns:
            JWT token字符串
        """
        expiration = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
        payload = {
            'user_id': user_id,
            'username': username,
            'exp': expiration,
            'iat': datetime.utcnow()
        }
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return token
    
    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """
        验证JWT token
        
        Args:
            token: JWT token字符串
            
        Returns:
            解码后的payload，如果无效则返回None
        """
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"无效的Token: {e}")
            return None
    
    @staticmethod
    def get_user_id_from_token(token: str) -> Optional[str]:
        """
        从token中提取用户ID
        
        Args:
            token: JWT token字符串
            
        Returns:
            用户ID，如果token无效则返回None
        """
        payload = AuthService.verify_token(token)
        if payload:
            return payload.get('user_id')
        return None










