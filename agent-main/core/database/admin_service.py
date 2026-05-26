"""
管理员服务
===========
处理所有管理员业务逻辑
基于实际的数据库表结构：users, conversations, messages, resources
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
import logging

logger = logging.getLogger(__name__)

# 中国时区 UTC+8
CHINA_TIMEZONE = timezone(timedelta(hours=8))

def get_local_now():
    """获取中国本地时间"""
    return datetime.now(CHINA_TIMEZONE).replace(tzinfo=None)


class AdminService:
    """管理员服务类"""

    def __init__(self, get_session_func):
        """
        初始化管理员服务

        Args:
            get_session_func: 获取数据库会话的函数
        """
        self.get_session = get_session_func

    def _get_session(self) -> Session:
        """获取数据库会话"""
        return self.get_session()

    # ==================== 用户管理 ====================

    def get_all_users(self, skip: int = 0, limit: int = 100, search: Optional[str] = None) -> Dict[str, Any]:
        """获取所有用户列表（含统计信息）"""
        from core.database.models import User, Conversation, Message

        session = self._get_session()
        try:
            # 构建基础查询
            base_query = session.query(
                User.user_id,
                User.username,
                User.email,
                User.nickname,
                User.created_at,
                User.last_login,
                User.is_active,
                User.subscription_tier,
                func.count(Conversation.conversation_id).label('session_count'),
                func.count(Message.message_id).label('message_count')
            ).outerjoin(
                Conversation, User.user_id == Conversation.user_id
            ).outerjoin(
                Message, Conversation.conversation_id == Message.conversation_id
            ).group_by(
                User.user_id
            )

            # 添加搜索条件
            if search:
                search_pattern = f"%{search}%"
                logger.info(f"🔍 搜索参数接收: search='{search}', pattern='{search_pattern}'")
                base_query = base_query.filter(
                    (User.username.ilike(search_pattern)) |
                    (User.email.ilike(search_pattern)) |
                    (User.nickname.ilike(search_pattern))
                )
                logger.debug(f"🔍 搜索用户: {search}")
            else:
                logger.info(f"📋 获取所有用户（skip={skip}, limit={limit}）- 无搜索条件")

            # 获取总数
            count_query = session.query(func.count(User.user_id))
            if search:
                count_query = count_query.filter(
                    (User.username.ilike(search_pattern)) |
                    (User.email.ilike(search_pattern)) |
                    (User.nickname.ilike(search_pattern))
                )
            total = count_query.scalar() or 0
            logger.info(f"📊 搜索总数: {total} (search='{search}')")

            # 应用排序、分页
            query = base_query.order_by(desc(User.created_at)).offset(skip).limit(limit)

            users = query.all()

            user_list = []
            for row in users:
                user_list.append({
                    "user_id": row.user_id,
                    "username": row.username,
                    "email": row.email,
                    "nickname": row.nickname,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_login": row.last_login.isoformat() if row.last_login else None,
                    "is_active": row.is_active,
                    "subscription_tier": row.subscription_tier,
                    "session_count": row.session_count or 0,
                    "message_count": row.message_count or 0
                })

            logger.info(f"✅ 返回用户数: {len(user_list)}, 用户名列表: {[u['username'] for u in user_list]}")

            return {
                "users": user_list,
                "total": total,
                "skip": skip,
                "limit": limit
            }
        except Exception as e:
            logger.error(f"❌ 获取用户列表失败: {e}")
            return {
                "users": [],
                "total": 0,
                "skip": skip,
                "limit": limit
            }
        finally:
            session.close()

    def get_user_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户详细信息"""
        from core.database.models import User, Conversation

        session = self._get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()

            if not user:
                return None

            # 获取用户的会话列表
            conversations = session.query(Conversation).filter(
                Conversation.user_id == user_id
            ).order_by(desc(Conversation.created_at)).limit(20).all()

            return {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "nickname": user.nickname,
                "avatar_url": user.avatar_url,
                "bio": user.bio,
                "location": user.location,
                "school": user.school,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "is_active": user.is_active,
                "subscription_tier": user.subscription_tier,
                "max_conversations": user.max_conversations,
                "total_plans_created": user.total_plans_created,
                "conversations": [conv.to_summary_dict() for conv in conversations]
            }
        finally:
            session.close()

    def delete_user(self, user_id: str, admin_user_id: str) -> bool:
        """删除用户（包括所有数据）"""
        from core.database.models import User

        session = self._get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                session.delete(user)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            print(f"删除用户失败: {e}")
            return False
        finally:
            session.close()

    def toggle_user_status(self, user_id: str, is_active: bool, admin_user_id: str) -> bool:
        """启用/禁用用户"""
        from core.database.models import User

        session = self._get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.is_active = is_active
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            print(f"切换用户状态失败: {e}")
            return False
        finally:
            session.close()

    # ==================== 会话管理 ====================

    def get_all_sessions(self, skip: int = 0, limit: int = 100,
                         status: Optional[str] = None) -> Dict[str, Any]:
        """获取所有会话列表"""
        from core.database.models import Conversation, User, Message

        session = self._get_session()
        try:
            # 构建基础查询
            base_query = session.query(Conversation).join(
                User, Conversation.user_id == User.user_id
            )

            # 状态筛选
            if status:
                base_query = base_query.filter(Conversation.status == status)

            # 获取总数
            total = base_query.count()

            # 构建详细查询
            query = session.query(
                Conversation.conversation_id,
                Conversation.user_id,
                User.username,
                Conversation.title,
                Conversation.destination,
                Conversation.status,
                Conversation.created_at,
                Conversation.updated_at,
                Conversation.message_count
            ).join(
                User, Conversation.user_id == User.user_id
            )

            if status:
                query = query.filter(Conversation.status == status)

            # 分页和排序
            conversations = query.order_by(desc(Conversation.created_at)).offset(skip).limit(limit).all()

            session_list = []
            for row in conversations:
                session_list.append({
                    "conversation_id": row.conversation_id,
                    "user_id": row.user_id,
                    "username": row.username,
                    "title": row.title,
                    "destination": row.destination,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "message_count": row.message_count or 0
                })

            return {
                "sessions": session_list,
                "total": total,
                "skip": skip,
                "limit": limit
            }
        finally:
            session.close()

    def delete_session(self, conversation_id: str, admin_user_id: str) -> bool:
        """删除会话（同时删除数据库记录和JSON文件）"""
        from core.database.models import Conversation

        session = self._get_session()
        try:
            # 查询会话信息（需要获取 user_id）
            conv = session.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            ).first()

            if conv:
                user_id = conv.user_id

                # 1. 删除数据库记录
                session.delete(conv)
                session.commit()
                logger.info(f"✅ 数据库记录已删除: conversation_id={conversation_id}, user_id={user_id}")

                # 2. 同步删除 JSON 文件
                try:
                    from core.user_system.conversation_repository import ConversationRepository
                    conv_repo = ConversationRepository()
                    result = conv_repo.delete_conversation(user_id, conversation_id, permanently=True)

                    if result.get("success"):
                        logger.info(f"✅ JSON文件已删除: conversation_id={conversation_id}")
                    else:
                        logger.warning(f"⚠️  JSON文件删除失败: {result.get('message')}")
                except Exception as json_error:
                    logger.error(f"❌ 删除JSON文件时出错: {json_error}")

                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"❌ 删除会话失败: {e}")
            return False
        finally:
            session.close()

    # ==================== 系统监控 ====================

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """获取仪表板统计数据"""
        from core.database.models import User, Conversation, Message

        session = self._get_session()
        try:
            # 用户统计
            total_users = session.query(func.count(User.user_id)).scalar() or 0

            # 24小时活跃用户（有创建会话的用户）
            active_users_24h = session.query(func.count(func.distinct(Conversation.user_id))).filter(
                Conversation.created_at >= get_local_now() - timedelta(hours=24)
            ).scalar() or 0

            # 会话统计
            total_sessions = session.query(func.count(Conversation.conversation_id)).scalar() or 0
            active_sessions = session.query(func.count(Conversation.conversation_id)).filter(
                Conversation.status == 'active'
            ).scalar() or 0
            archived_sessions = session.query(func.count(Conversation.conversation_id)).filter(
                Conversation.status == 'archived'
            ).scalar() or 0

            # 消息统计
            total_messages = session.query(func.count(Message.message_id)).scalar() or 0

            # 近期趋势（最近7天）
            daily_sessions = []
            for i in range(6, -1, -1):
                date = get_local_now().replace(hour=0, minute=0, second=0, microsecond=0)
                date = date - timedelta(days=i)

                count = session.query(func.count(Conversation.conversation_id)).filter(
                    and_(
                        func.date(Conversation.created_at) == date.date()
                    )
                ).scalar() or 0

                daily_sessions.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "count": count
                })

            return {
                "users": {
                    "total": total_users,
                    "active_24h": active_users_24h
                },
                "sessions": {
                    "total": total_sessions,
                    "active": active_sessions,
                    "archived": archived_sessions
                },
                "messages": {
                    "total": total_messages
                },
                "trends": {
                    "daily_sessions": daily_sessions
                }
            }
        finally:
            session.close()

    # ==================== 系统配置 ====================

    def get_all_configs(self) -> Dict[str, Any]:
        """获取所有系统配置（从数据库和环境变量）"""
        import os
        from core.database.admin_models import SystemConfig

        session = self._get_session()
        try:
            # 从数据库获取自定义配置
            db_configs = session.query(SystemConfig).all()
            config_map = {config.key: config.value for config in db_configs}

            # 定义所有配置项的默认值和来源
            configs = {
                "AI服务": [
                    {
                        "key": "QWEN_MODEL_FAST",
                        "value": config_map.get("QWEN_MODEL_FAST", os.getenv("QWEN_MODEL_FAST", "qwen-turbo")),
                        "description": "快速推理模型（用于日常对话）",
                        "category": "AI服务",
                        "editable": True
                    },
                    {
                        "key": "QWEN_MODEL_DEEP",
                        "value": config_map.get("QWEN_MODEL_DEEP", os.getenv("QWEN_MODEL_DEEP", "qwen-plus")),
                        "description": "深度推理模型（用于复杂规划）",
                        "category": "AI服务",
                        "editable": True
                    },
                    {
                        "key": "DEFAULT_MODEL",
                        "value": config_map.get("DEFAULT_MODEL", os.getenv("DEFAULT_MODEL", "qwen-max")),
                        "description": "默认AI模型",
                        "category": "AI服务",
                        "editable": True
                    },
                    {
                        "key": "MAX_TOKENS",
                        "value": config_map.get("MAX_TOKENS", os.getenv("MAX_TOKENS", "8000")),
                        "description": "最大Token数",
                        "category": "AI服务",
                        "editable": True
                    }
                ],
                "地图服务": [
                    {
                        "key": "GAODE_REST_API_KEY",
                        "value": self._mask_api_key(config_map.get("GAODE_REST_API_KEY") or os.getenv("GAODE_REST_API_KEY", "")),
                        "description": "高德地图 REST API Key",
                        "category": "地图服务",
                        "editable": True,
                        "sensitive": True
                    },
                    {
                        "key": "GAODE_JS_API_KEY",
                        "value": self._mask_api_key(config_map.get("GAODE_JS_API_KEY") or os.getenv("GAODE_JS_API_KEY", "")),
                        "description": "高德地图 JS API Key",
                        "category": "地图服务",
                        "editable": True,
                        "sensitive": True
                    }
                ],
                "搜索服务": [
                    {
                        "key": "TAVILY_API_KEY",
                        "value": self._mask_api_key(config_map.get("TAVILY_API_KEY") or os.getenv("TAVILY_API_KEY", "")),
                        "description": "Tavily 搜索 API Key",
                        "category": "搜索服务",
                        "editable": True,
                        "sensitive": True
                    }
                ],
                "系统设置": [
                    {
                        "key": "MAX_CONVERSATIONS",
                        "value": config_map.get("MAX_CONVERSATIONS", "10"),
                        "description": "默认用户最大会话数",
                        "category": "系统设置",
                        "editable": True
                    },
                    {
                        "key": "ENABLE_AUTO_ARCHIVE",
                        "value": config_map.get("ENABLE_AUTO_ARCHIVE", "true"),
                        "description": "启用自动归档（true/false）",
                        "category": "系统设置",
                        "editable": True
                    },
                    {
                        "key": "ARCHIVE_AFTER_DAYS",
                        "value": config_map.get("ARCHIVE_AFTER_DAYS", "30"),
                        "description": "自动归档天数",
                        "category": "系统设置",
                        "editable": True
                    }
                ]
            }

            return configs
        finally:
            session.close()

    def _mask_api_key(self, key: str) -> str:
        """隐藏API Key的部分内容"""
        if not key or len(key) < 8:
            return "***" if key else "未设置"
        # 如果已经包含***，说明已经masked过了
        if "***" in key:
            return key
        # 否则进行mask
        return "***" + key[-4:]

    def update_config(self, key: str, value: str, admin_user_id: str) -> Dict[str, Any]:
        """更新系统配置到数据库"""
        from core.database.admin_models import SystemConfig

        session = self._get_session()
        try:
            # 查找是否已存在该配置
            config = session.query(SystemConfig).filter(SystemConfig.key == key).first()

            if config:
                # 更新现有配置
                old_value = config.value
                config.value = value
                config.updated_at = get_local_now()
                config.updated_by = admin_user_id
            else:
                # 创建新配置
                config = SystemConfig(
                    key=key,
                    value=value,
                    category=self._get_config_category(key),
                    description=self._get_config_description(key),
                    updated_at=get_local_now(),
                    updated_by=admin_user_id
                )
                session.add(config)

            session.commit()

            # 记录操作日志（如果需要）
            print(f"[{admin_user_id}] 更新配置: {key} = {value}")

            return {
                "success": True,
                "message": "配置更新成功"
            }
        except Exception as e:
            session.rollback()
            print(f"更新配置失败: {e}")
            return {
                "success": False,
                "message": f"更新失败: {str(e)}"
            }
        finally:
            session.close()

    def _get_config_category(self, key: str) -> str:
        """获取配置的分类"""
        category_map = {
            "QWEN_MODEL_FAST": "AI服务",
            "QWEN_MODEL_DEEP": "AI服务",
            "DEFAULT_MODEL": "AI服务",
            "MAX_TOKENS": "AI服务",
            "GAODE_REST_API_KEY": "地图服务",
            "GAODE_JS_API_KEY": "地图服务",
            "TAVILY_API_KEY": "搜索服务",
            "MAX_CONVERSATIONS": "系统设置",
            "ENABLE_AUTO_ARCHIVE": "系统设置",
            "ARCHIVE_AFTER_DAYS": "系统设置",
        }
        return category_map.get(key, "其他")

    def _get_config_description(self, key: str) -> str:
        """获取配置的描述"""
        desc_map = {
            "QWEN_MODEL_FAST": "快速推理模型（用于日常对话）",
            "QWEN_MODEL_DEEP": "深度推理模型（用于复杂规划）",
            "DEFAULT_MODEL": "默认AI模型",
            "MAX_TOKENS": "最大Token数",
            "GAODE_REST_API_KEY": "高德地图 REST API Key",
            "GAODE_JS_API_KEY": "高德地图 JS API Key",
            "TAVILY_API_KEY": "Tavily 搜索 API Key",
            "MAX_CONVERSATIONS": "默认用户最大会话数",
            "ENABLE_AUTO_ARCHIVE": "启用自动归档（true/false）",
            "ARCHIVE_AFTER_DAYS": "自动归档天数",
        }
        return desc_map.get(key, "")

    # ==================== 日志管理 ====================

    def get_audit_logs(self, skip: int = 0, limit: int = 100,
                       action: Optional[str] = None,
                       admin_user: Optional[str] = None) -> Dict[str, Any]:
        """获取审计日志"""
        from core.database.admin_models import AuditLog

        session = self._get_session()
        try:
            # 构建查询
            query = session.query(AuditLog)

            # 筛选条件
            if action:
                query = query.filter(AuditLog.action == action)
            if admin_user:
                query = query.filter(AuditLog.admin_user_id == admin_user)

            # 获取总数
            total = query.count()

            # 排序和分页
            query = query.order_by(AuditLog.timestamp.desc())
            query = query.offset(skip).limit(limit)

            # 获取数据
            logs = query.all()

            # 转换为字典
            log_list = []
            for log in logs:
                log_list.append({
                    "id": log.id,
                    "admin_user_id": log.admin_user_id,
                    "action": log.action,
                    "resource_type": log.resource_type or "N/A",
                    "resource_id": log.resource_id or "N/A",
                    "details": log.details or "",
                    "ip_address": log.ip_address,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None
                })

            return {
                "logs": log_list,
                "total": total,
                "skip": skip,
                "limit": limit
            }
        except Exception as e:
            logger.error(f"❌ 获取审计日志失败: {e}")
            return {
                "logs": [],
                "total": 0,
                "skip": skip,
                "limit": limit
            }
        finally:
            session.close()

    def create_audit_log(self, admin_user_id: str, action: str,
                        resource_type: str = None, resource_id: str = None,
                        details: str = None, ip_address: str = None) -> bool:
        """创建审计日志"""
        from core.database.admin_models import AuditLog

        session = self._get_session()
        try:
            log = AuditLog(
                admin_user_id=admin_user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address
            )
            session.add(log)
            session.commit()
            logger.debug(f"✅ 审计日志已记录: {action} by {admin_user_id}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"❌ 记录审计日志失败: {e}")
            return False
        finally:
            session.close()
