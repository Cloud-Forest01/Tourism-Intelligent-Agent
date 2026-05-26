"""
用户认证 API 路由
提供用户注册、登录、获取用户信息等接口
"""
from fastapi import APIRouter, HTTPException, Depends, Header, Request, UploadFile, File
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
import logging
import os
import uuid
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/auth",
    tags=["认证"]
)

# ==================== 请求/响应模型 ====================

class RegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=20, description="用户名")
    password: str = Field(..., min_length=6, max_length=50, description="密码")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    nickname: Optional[str] = Field(None, description="昵称")


class LoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class AuthResponse(BaseModel):
    """认证响应"""
    success: bool
    message: str
    user_id: Optional[str] = None
    access_token: Optional[str] = None
    user: Optional[dict] = None


class UpdateProfileRequest(BaseModel):
    """更新用户资料请求"""
    nickname: Optional[str] = Field(None, min_length=1, max_length=50, description="昵称")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    avatar_url: Optional[str] = Field(None, description="头像URL")


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    user_id: str
    username: str
    email: Optional[str]
    nickname: str
    avatar_url: Optional[str]
    is_active: bool
    is_verified: bool
    subscription_tier: str
    max_conversations: int
    current_conversation_count: int
    total_plans_created: int
    favorite_destinations: list


# ==================== 依赖注入 ====================

def get_auth_service(request: Request):
    """从应用状态获取认证服务"""
    return request.app.state.auth_service


def get_db_repository(request: Request):
    """从应用状态获取数据库仓储"""
    return request.app.state.db_repository


async def get_current_user(
    authorization: str = Header(None),
    auth_service=Depends(get_auth_service)
) -> dict:
    """
    从 Authorization header 获取当前用户

    Args:
        authorization: Bearer token

    Returns:
        dict: 用户信息

    Raises:
        HTTPException: 认证失败
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="无效的认证格式")

    token = authorization[7:]  # 移除 "Bearer " 前缀

    user_data = auth_service.verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    return user_data


# ==================== API 路由 ====================

@router.post("/register", response_model=AuthResponse)
async def register(
    request: RegisterRequest,
    auth_service=Depends(get_auth_service)
):
    """
    用户注册

    Args:
        request: 注册请求
        auth_service: 认证服务

    Returns:
        AuthResponse: 注册结果
    """
    result = auth_service.register(
        username=request.username,
        password=request.password,
        email=request.email,
        nickname=request.nickname or "旅行者"
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    auth_service=Depends(get_auth_service)
):
    """
    用户登录

    Args:
        request: 登录请求
        auth_service: 认证服务

    Returns:
        AuthResponse: 登录结果
    """
    result = auth_service.login(
        username=request.username,
        password=request.password
    )

    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])

    return result


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db_repository=Depends(get_db_repository)
):
    """
    获取当前登录用户的信息

    Args:
        current_user: 当前用户
        db_repository: 数据库仓储

    Returns:
        UserInfoResponse: 用户信息
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="未认证")

    user_id = current_user.get("user_id")
    user = db_repository.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 获取当前会话数
    quota_info = db_repository.get_quota_info(user_id)

    return UserInfoResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        subscription_tier=user.subscription_tier,
        max_conversations=user.max_conversations,
        current_conversation_count=quota_info.get("current", 0),
        total_plans_created=user.total_plans_created,
        favorite_destinations=user.favorite_destinations or []
    )


@router.post("/logout")
async def logout():
    """
    用户登出

    注意：JWT 是无状态的，登出主要在前端处理（删除 token）
    后端可以实现 token 黑名单（可选）
    """
    return {"success": True, "message": "登出成功"}


@router.post("/verify-token")
async def verify_token(
    token: str,
    auth_service=Depends(get_auth_service)
):
    """
    验证 JWT 令牌

    Args:
        token: JWT 令牌
        auth_service: 认证服务

    Returns:
        dict: 验证结果
    """
    result = auth_service.verify_token(token)

    if result:
        return {"success": True, "user": result}
    else:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")


@router.put("/update", response_model=AuthResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
    db_repository=Depends(get_db_repository)
):
    """
    更新用户资料

    Args:
        request: 更新请求
        current_user: 当前用户
        db_repository: 数据库仓储

    Returns:
        AuthResponse: 更新结果
    """
    user_id = current_user.get("user_id")

    # 构建更新数据（只包含非空字段）
    update_data = {}
    if request.nickname is not None:
        update_data["nickname"] = request.nickname
    if request.email is not None:
        update_data["email"] = request.email
    if request.avatar_url is not None:
        update_data["avatar_url"] = request.avatar_url

    if not update_data:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")

    # 执行更新
    success = db_repository.update_user_profile(user_id, **update_data)

    if not success:
        raise HTTPException(status_code=500, detail="更新失败")

    # 获取更新后的用户信息
    user = db_repository.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return AuthResponse(
        success=True,
        message="资料更新成功",
        user_id=user.user_id,
        user={
            "user_id": user.user_id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "subscription_tier": user.subscription_tier
        }
    )


@router.post("/upload-avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db_repository=Depends(get_db_repository)
):
    """
    上传用户头像

    Args:
        file: 上传的图片文件
        current_user: 当前用户
        db_repository: 数据库仓储

    Returns:
        dict: 包含头像URL的响应
    """
    # 验证文件类型
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型。支持的类型: {', '.join(allowed_types)}"
        )

    # 验证文件大小（限制为5MB）
    max_size = 5 * 1024 * 1024  # 5MB
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="文件大小不能超过5MB")

    # 重置文件指针
    await file.seek(0)

    # 创建上传目录（使用绝对路径）
    import os
    base_dir = Path(__file__).parent.parent  # 项目根目录
    upload_dir = base_dir / "static" / "uploads" / "avatars"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名
    file_ext = Path(file.filename).suffix or ".jpg"
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = upload_dir / unique_filename

    # 保存文件
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"保存头像文件失败: {e}")
        raise HTTPException(status_code=500, detail="文件保存失败")

    # 生成访问URL
    avatar_url = f"/static/uploads/avatars/{unique_filename}"

    # 更新用户头像
    user_id = current_user.get("user_id")
    success = db_repository.update_user_profile(user_id, avatar_url=avatar_url)

    if not success:
        raise HTTPException(status_code=500, detail="更新头像失败")

    logger.info(f"用户 {user_id} 上传头像成功: {avatar_url}")

    return {
        "success": True,
        "message": "头像上传成功",
        "avatar_url": avatar_url
    }


# ==================== 密码重置 ====================

class ResetPasswordRequest(BaseModel):
    """密码重置请求"""
    identifier: str = Field(..., description="用户名或邮箱")
    new_password: str = Field(..., min_length=6, max_length=50, description="新密码")


@router.post("/reset-password", response_model=AuthResponse)
async def reset_password(
    request: ResetPasswordRequest,
    auth_service=Depends(get_auth_service),
    db_repository=Depends(get_db_repository)
):
    """
    简单密码重置（无需邮箱验证）

    Args:
        request: 重置请求（包含用户名/邮箱和新密码）
        auth_service: 认证服务
        db_repository: 数据库仓储

    Returns:
        AuthResponse: 重置结果
    """
    # 通过用户名或邮箱查找用户
    user = db_repository.get_user_by_username(request.identifier)
    if not user:
        user = db_repository.get_user_by_email(request.identifier)

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 更新密码
    success = db_repository.update_user_password(
        user.user_id,
        auth_service.hash_password(request.new_password)
    )

    if not success:
        raise HTTPException(status_code=500, detail="密码重置失败")

    logger.info(f"用户 {user.user_id} ({user.username}) 密码已重置")

    return {
        "success": True,
        "message": "密码重置成功，请使用新密码登录",
        "user_id": user.user_id
    }
