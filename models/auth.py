"""
用户认证模型
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime


class UserAccount(BaseModel):
    """用户账户信息"""
    user_id: str = Field(..., description="用户唯一标识")
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: Optional[EmailStr] = Field(None, description="邮箱地址")
    password_hash: str = Field(..., description="密码哈希值")
    created_at: Optional[datetime] = Field(default_factory=datetime.now, description="创建时间")
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, description="更新时间")
    is_active: bool = Field(default=True, description="账户是否激活")
    last_login: Optional[datetime] = Field(None, description="最后登录时间")


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: Optional[EmailStr] = Field(None, description="邮箱地址（可选）")
    password: str = Field(..., min_length=6, max_length=100, description="密码（至少6位）")


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str = Field(..., description="JWT访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    expires_in: int = Field(default=3600, description="令牌过期时间（秒）")


class UserInfo(BaseModel):
    """用户信息（不包含敏感信息）"""
    user_id: str
    username: str
    email: Optional[str] = None
    created_at: Optional[datetime] = None
    is_active: bool = True

