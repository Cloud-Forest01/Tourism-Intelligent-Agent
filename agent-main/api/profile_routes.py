"""
用户资料 API 路由
提供用户资料更新、头像上传等接口
"""
from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, Form
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/profile",
    tags=["用户资料"]
)


# ==================== 依赖注入 ====================

def get_db_repository(request: Request):
    """从应用状态获取数据库仓储"""
    return request.app.state.db_repository


def get_auth_service(request: Request):
    """从应用状态获取认证服务"""
    return request.app.state.auth_service


async def get_current_user(
    request: Request,
    auth_service=Depends(get_auth_service)
) -> dict:
    """从 Authorization header 获取当前用户"""
    # 从请求头获取 authorization
    authorization = request.headers.get("Authorization")

    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="无效的认证格式")

    token = authorization[7:]
    user_data = auth_service.verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    return user_data


# ==================== API 路由 ====================

@router.post("/update-with-avatar")
async def update_profile_with_avatar(
    nickname: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = None,
    current_user: dict = Depends(get_current_user),
    db_repository=Depends(get_db_repository)
):
    """
    统一更新用户资料（包括头像上传）

    Args:
        nickname: 昵称（可选）
        email: 邮箱（可选）
        avatar: 头像文件（可选）
        current_user: 当前用户
        db_repository: 数据库仓储

    Returns:
        dict: 更新结果
    """
    user_id = current_user.get("user_id")
    update_data = {}

    # 处理头像上传
    if avatar:
        # 验证文件类型
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
        if avatar.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型。支持的类型: {', '.join(allowed_types)}"
            )

        # 验证文件大小（限制为5MB）
        max_size = 5 * 1024 * 1024
        content = await avatar.read()
        if len(content) > max_size:
            raise HTTPException(status_code=400, detail="文件大小不能超过5MB")

        # 创建上传目录
        base_dir = Path(__file__).parent.parent
        upload_dir = base_dir / "static" / "uploads" / "avatars"
        upload_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一文件名
        file_ext = Path(avatar.filename).suffix or ".jpg"
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
        update_data["avatar_url"] = avatar_url
        logger.info(f"用户 {user_id} 上传头像成功: {avatar_url}")

    # 处理昵称和邮箱
    if nickname is not None:
        update_data["nickname"] = nickname.strip()
    if email is not None:
        update_data["email"] = email.strip()

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

    return {
        "success": True,
        "message": "资料更新成功",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "avatar_url": user.avatar_url
        }
    }
