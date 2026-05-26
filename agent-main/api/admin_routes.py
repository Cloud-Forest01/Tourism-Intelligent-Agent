"""
管理员系统API路由
===============
提供所有管理员功能的API接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

# 中国时区 UTC+8
CHINA_TIMEZONE = timezone(timedelta(hours=8))

def get_local_now():
    """获取中国本地时间"""
    return datetime.now(CHINA_TIMEZONE).replace(tzinfo=None)

# 创建路由器
admin_router = APIRouter(prefix="/api/admin", tags=["管理员系统"])


# ==================== 数据模型 ====================

class AdminLoginRequest(BaseModel):
    """管理员登录请求"""
    username: str = Field(..., description="管理员用户名")
    password: str = Field(..., description="管理员密码")


class AdminLoginResponse(BaseModel):
    """管理员登录响应"""
    access_token: str
    token_type: str = "bearer"
    admin_id: str
    role: str


class DashboardStatsResponse(BaseModel):
    """仪表板统计响应"""
    users: dict
    sessions: dict
    messages: dict
    trends: dict


class UserListResponse(BaseModel):
    """用户列表响应"""
    users: List[dict]
    total: int
    skip: int
    limit: int


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[dict]
    total: int
    skip: int
    limit: int


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    key: str = Field(..., description="配置键")
    value: str = Field(..., description="配置值")


# ==================== 认证依赖 ====================

# 全局变量，在应用启动时初始化
admin_service = None
db_repository_global = None


def get_admin_service():
    """获取管理员服务实例"""
    return admin_service


def set_db_repository(db_repo):
    """设置全局数据库仓库实例"""
    global db_repository_global
    db_repository_global = db_repo


# 临时简化：使用普通用户表作为管理员表
# 实际应该有独立的管理员表
async def verify_admin(username: str, password: str) -> Optional[dict]:
    """验证管理员身份"""
    # 临时方案：使用任意已注册用户作为管理员（仅用于测试）
    # 生产环境应该有独立的管理员表和真正的密码验证

    if not db_repository_global:
        # 如果没有全局实例，创建临时实例
        from core.database.repository import DatabaseRepository
        db_repo = DatabaseRepository()
        db = db_repo.get_session()
    else:
        db = db_repository_global.get_session()
    try:
        # 使用认证服务验证用户（包含密码验证）
        from core.auth.auth_service import AuthService
        auth_service = AuthService(db_repository_global or db_repo)

        # 使用 login 方法验证用户名和密码
        result = auth_service.login(username, password)

        if result.get("success"):
            return {
                "user_id": result["user_id"],
                "username": result["user"]["username"],
                "email": result["user"]["email"],
                "role": "admin"  # 默认管理员角色
            }
        return None
    except Exception as e:
        logger.error(f"管理员验证失败: {e}")
        return None
    finally:
        if not db_repository_global:
            db.close()


# OAuth2 scheme for Bearer token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/admin/login")


async def get_current_admin(token: str = Depends(oauth2_scheme)) -> dict:
    """获取当前管理员"""
    # 临时简化：直接验证token
    # 生产环境应该使用JWT验证
    if not token:
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    # TODO: 实现JWT验证
    # 临时返回一个假的管理员对象
    return {
        "user_id": "admin_temp",
        "username": "admin",
        "role": "super_admin"
    }


# ==================== 管理员认证接口 ====================

@admin_router.post("/login", response_model=AdminLoginResponse)
async def admin_login(request: AdminLoginRequest, req: Request):
    """管理员登录"""
    # 验证管理员身份
    admin = await verify_admin(request.username, request.password)

    if not admin:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # TODO: 生成JWT token
    # 临时：返回一个假token
    token = f"admin_token_{get_local_now().timestamp()}"

    # 记录审计日志
    service = get_admin_service()
    if service:
        client_ip = req.client.host if req.client else "unknown"
        service.create_audit_log(
            admin_user_id=admin["user_id"],
            action="login",
            resource_type="system",
            resource_id="N/A",
            details=f"管理员登录: {request.username}",
            ip_address=client_ip
        )

    return AdminLoginResponse(
        access_token=token,
        admin_id=admin["user_id"],
        role=admin["role"]
    )


@admin_router.get("/me")
async def get_admin_info(current_admin: dict = Depends(get_current_admin)):
    """获取当前管理员信息"""
    return {
        "success": True,
        "data": current_admin
    }


# ==================== 用户管理接口 ====================

@admin_router.get("/users")
async def get_users(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词（用户名或邮箱）"),
    current_admin: dict = Depends(get_current_admin)
):
    """获取用户列表"""
    logger.info(f"📥 收到用户列表请求: skip={skip}, limit={limit}, search='{search}'")

    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    result = service.get_all_users(skip=skip, limit=limit, search=search)
    logger.info(f"📤 返回结果: {result.get('total')} 个用户")
    return {
        "success": True,
        "data": result
    }


@admin_router.get("/users/{user_id}")
async def get_user_details(
    user_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """获取用户详细信息"""
    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    user = service.get_user_details(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {
        "success": True,
        "data": user
    }


@admin_router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin)
):
    """删除用户"""
    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    success = service.delete_user(user_id, current_admin["user_id"])
    if success:
        # 记录审计日志
        client_ip = request.client.host if request.client else "unknown"
        service.create_audit_log(
            admin_user_id=current_admin["user_id"],
            action="delete_user",
            resource_type="user",
            resource_id=user_id,
            details=f"删除用户: {user_id}",
            ip_address=client_ip
        )
        return {
            "success": True,
            "message": "用户删除成功"
        }
    else:
        raise HTTPException(status_code=500, detail="删除用户失败")


# ==================== 会话管理接口 ====================

@admin_router.get("/sessions")
async def get_sessions(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选: active/archived/deleted"),
    current_admin: dict = Depends(get_current_admin)
):
    """获取会话列表"""
    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    result = service.get_all_sessions(skip=skip, limit=limit, status=status)
    return {
        "success": True,
        "data": result
    }


@admin_router.delete("/sessions/{conversation_id}")
async def delete_session(
    conversation_id: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin)
):
    """删除会话"""
    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    success = service.delete_session(conversation_id, current_admin["user_id"])
    if success:
        # 记录审计日志
        client_ip = request.client.host if request.client else "unknown"
        service.create_audit_log(
            admin_user_id=current_admin["user_id"],
            action="delete_session",
            resource_type="session",
            resource_id=conversation_id,
            details=f"删除会话: {conversation_id}",
            ip_address=client_ip
        )
        return {
            "success": True,
            "message": "会话删除成功"
        }
    else:
        raise HTTPException(status_code=500, detail="删除会话失败")


# ==================== 仪表板统计接口 ====================

@admin_router.get("/dashboard")
async def get_dashboard_stats(
    current_admin: dict = Depends(get_current_admin)
):
    """获取仪表板统计数据"""
    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    stats = service.get_dashboard_stats()
    return {
        "success": True,
        "data": stats
    }


# ==================== 系统配置接口 ====================

@admin_router.get("/configs")
async def get_configs(
    current_admin: dict = Depends(get_current_admin)
):
    """获取所有系统配置"""
    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    configs = service.get_all_configs()
    return {
        "success": True,
        "data": configs
    }


@admin_router.put("/configs")
async def update_config(
    request: ConfigUpdateRequest,
    req: Request,
    current_admin: dict = Depends(get_current_admin)
):
    """更新系统配置"""
    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    result = service.update_config(request.key, request.value, current_admin["user_id"])

    if result.get("success"):
        # 记录审计日志
        client_ip = req.client.host if req.client else "unknown"
        service.create_audit_log(
            admin_user_id=current_admin["user_id"],
            action="update_config",
            resource_type="config",
            resource_id=request.key,
            details=f"修改配置: {request.key} = {request.value}",
            ip_address=client_ip
        )
        return {
            "success": True,
            "message": result.get("message", "配置更新成功")
        }
    else:
        return {
            "success": False,
            "message": result.get("message", "更新失败")
        }


# ==================== 日志管理接口 ====================

@admin_router.get("/audit-logs")
async def get_audit_logs(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    action: Optional[str] = Query(None, description="操作类型筛选"),
    current_admin: dict = Depends(get_current_admin)
):
    """获取审计日志"""
    service = get_admin_service()
    if not service:
        raise HTTPException(status_code=503, detail="管理员服务未初始化")

    logs = service.get_audit_logs(skip=skip, limit=limit, action=action)
    return {
        "success": True,
        "data": logs
    }


# ==================== 数据同步接口 ====================

@admin_router.post("/sync-data")
async def sync_data_from_json(
    current_admin: dict = Depends(get_current_admin)
):
    """手动同步JSON数据到数据库"""
    import subprocess
    import sys
    from pathlib import Path

    try:
        # 获取备份脚本路径
        script_path = Path(__file__).parent.parent / "backup_conversations_to_db.py"

        if not script_path.exists():
            raise HTTPException(status_code=500, detail="备份脚本不存在")

        # 运行备份脚本
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=300  # 5分钟超时
        )

        if result.returncode == 0:
            return {
                "success": True,
                "message": "数据同步成功",
                "output": result.stdout
            }
        else:
            logger.error(f"同步失败: {result.stderr}")
            return {
                "success": False,
                "message": f"同步失败: {result.stderr}",
                "output": result.stdout
            }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="同步超时（超过5分钟）")
    except Exception as e:
        logger.error(f"同步过程出错: {e}")
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


# ==================== 初始化函数 ====================

def init_admin_system(db_service):
    """初始化管理员系统"""
    global admin_service
    from core.database.admin_service import AdminService

    # 传递 get_session 方法引用
    admin_service = AdminService(db_service.get_session)
    logger.info("✅ 管理员服务初始化成功")


def get_admin_router() -> APIRouter:
    """获取管理员路由器"""
    return admin_router
