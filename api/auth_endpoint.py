"""
用户认证API端点 - 注册、登录、用户信息管理
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from pydantic import BaseModel
import uuid
from datetime import datetime

from models.auth import RegisterRequest, LoginRequest, LoginResponse, UserInfo, UserAccount
from services.auth import AuthService
from storage.impl.supabase_repository import SupabaseAuthRepository, SupabaseUserRepository
from services.utils.logger import get_logger

logger = get_logger("api.auth")

router = APIRouter(prefix="/auth", tags=["authentication"])


def get_auth_repository() -> SupabaseAuthRepository:
    """获取认证存储实例"""
    return SupabaseAuthRepository()


def get_user_repository() -> SupabaseUserRepository:
    """获取用户存储实例"""
    return SupabaseUserRepository()


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    从请求头中提取并验证JWT token，返回当前用户信息
    
    Args:
        authorization: Authorization请求头，格式为 "Bearer <token>"
        
    Returns:
        包含user_id和username的字典
        
    Raises:
        HTTPException: 如果token无效或缺失
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少认证令牌")
    
    try:
        # 提取token（格式：Bearer <token>）
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="无效的认证方案")
    except ValueError:
        raise HTTPException(status_code=401, detail="无效的认证令牌格式")
    
    # 验证token
    payload = AuthService.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="无效或过期的令牌")
    
    return {
        "user_id": payload.get("user_id"),
        "username": payload.get("username")
    }


@router.post("/register", response_model=LoginResponse)
async def register(request: RegisterRequest):
    """
    用户注册
    
    创建新用户账户，自动创建用户画像，并返回登录token
    """
    auth_repo = get_auth_repository()
    
    # 检查用户名是否已存在
    if auth_repo.username_exists(request.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 检查邮箱是否已存在（如果提供了邮箱）
    if request.email and auth_repo.email_exists(request.email):
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    
    try:
        # 生成用户ID
        user_id = str(uuid.uuid4())
        
        # 加密密码
        password_hash = AuthService.hash_password(request.password)
        
        # 创建用户账户
        user_account = UserAccount(
            user_id=user_id,
            username=request.username,
            email=request.email,
            password_hash=password_hash,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_active=True
        )
        
        # 保存账户信息（这会创建用户记录和账户信息）
        auth_repo.create_account(user_account)
        
        # 创建用户画像（使用UserRepository）
        # 注意：user_repo.save()会保留现有的metadata，不会覆盖账户信息
        user_repo = get_user_repository()
        from models.user import UserProfile, CEFRLevel
        
        # 先检查用户是否已存在（create_account已创建）
        user_profile = user_repo.get(user_id)
        if not user_profile:
            # 如果不存在，创建新用户画像
            user_profile = UserProfile(
                user_id=user_id,
                overall_score=0.0,
                cefr_level=CEFRLevel.A1
            )
            user_repo.save(user_profile)
        # 如果已存在，不需要再次保存（账户信息已在create_account中保存）
        
        logger.info(f"用户注册成功: {user_id} ({request.username})")
        
        # 生成token
        token = AuthService.generate_token(user_id, request.username)
        
        return LoginResponse(
            access_token=token,
            token_type="bearer",
            user_id=user_id,
            username=request.username,
            expires_in=3600 * 24  # 24小时
        )
        
    except Exception as e:
        logger.error(f"注册失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    用户登录
    
    验证用户名/邮箱和密码，返回JWT token
    """
    auth_repo = get_auth_repository()
    
    # 尝试通过用户名或邮箱查找账户
    user_account = None
    if "@" in request.username:
        # 看起来是邮箱
        user_account = auth_repo.get_account_by_email(request.username)
    else:
        # 用户名
        user_account = auth_repo.get_account_by_username(request.username)
    
    if not user_account:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    if not user_account.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    
    # 验证密码
    if not AuthService.verify_password(request.password, user_account.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 更新最后登录时间
    auth_repo.update_last_login(user_account.user_id)
    
    logger.info(f"用户登录成功: {user_account.user_id} ({user_account.username})")
    
    # 生成token
    token = AuthService.generate_token(user_account.user_id, user_account.username)
    
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_account.user_id,
        username=user_account.username,
        expires_in=3600 * 24  # 24小时
    )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    获取当前用户信息
    """
    auth_repo = get_auth_repository()
    user_account = auth_repo.get_account_by_user_id(current_user["user_id"])
    
    if not user_account:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return UserInfo(
        user_id=user_account.user_id,
        username=user_account.username,
        email=user_account.email,
        created_at=user_account.created_at,
        is_active=user_account.is_active
    )


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    用户登出
    
    注意：由于JWT是无状态的，这里主要是记录日志。
    实际的token失效需要客户端删除token。
    """
    logger.info(f"用户登出: {current_user['user_id']} ({current_user['username']})")
    return {"message": "登出成功"}

