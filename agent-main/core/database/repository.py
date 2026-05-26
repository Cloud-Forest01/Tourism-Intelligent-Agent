"""
数据库仓储层
提供数据库的 CRUD 操作接口
基于 SQLAlchemy，支持用户和会话的完整管理
"""
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timedelta
from sqlalchemy import create_engine, or_, and_, desc, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import IntegrityError
import logging

from .models import Base, User, Conversation, Message, Resource

logger = logging.getLogger(__name__)


class DatabaseRepository:
    """
    数据库仓储类

    功能：
    - 用户管理：注册、登录、查询
    - 会话管理：CRUD、归档、搜索
    - 消息管理：添加、查询
    - 资源管理：添加、查询
    - 配额管理：确保用户不超过会话限制
    """

    def __init__(self, database_url: str = "sqlite:///./data/trip_planner.db"):
        """
        初始化数据库连接

        Args:
            database_url: 数据库连接字符串
                - SQLite: sqlite:///./data/trip_planner.db
                - PostgreSQL: postgresql://user:pass@localhost/dbname
        """
        self.database_url = database_url

        # 创建引擎
        self.engine = create_engine(
            database_url,
            echo=False,  # 设置为 True 可以查看 SQL 语句
            pool_pre_ping=True,  # 检查连接有效性
            connect_args={"check_same_thread": False} if "sqlite" in database_url else {}
        )

        # 创建会话工厂
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        # 创建表（如果不存在）
        self._init_database()

        logger.info(f"✅ 数据库初始化完成: {database_url}")

    def _init_database(self):
        """初始化数据库表"""
        Base.metadata.create_all(bind=self.engine)

        # 创建管理员相关表
        try:
            from core.database.admin_models import Base as AdminBase
            AdminBase.metadata.create_all(bind=self.engine, checkfirst=True)
            logger.info("✅ 管理员数据库表创建成功")
        except Exception as e:
            logger.warning(f"⚠️ 创建管理员表时出错: {e}")

        logger.info("✅ 数据库表创建完成")

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()

    # ==================== 用户管理 ====================

    def create_user(
        self,
        username: str,
        password_hash: str,
        salt: str,
        email: Optional[str] = None,
        **profile_data
    ) -> Dict[str, Any]:
        """
        创建新用户

        Args:
            username: 用户名
            password_hash: 密码哈希
            salt: 盐值
            email: 邮箱
            **profile_data: 其他个人资料

        Returns:
            Dict: {"success": bool, "message": str, "user_id": Optional[str]}
        """
        session = self.get_session()
        try:
            # 检查用户名是否已存在
            existing = session.query(User).filter(User.username == username).first()
            if existing:
                return {"success": False, "message": "用户名已存在", "user_id": None}

            # 检查邮箱是否已存在
            if email:
                existing_email = session.query(User).filter(User.email == email).first()
                if existing_email:
                    return {"success": False, "message": "邮箱已被注册", "user_id": None}

            # 创建用户
            import secrets
            user_id = f"user_{secrets.token_hex(8)}"

            user = User(
                user_id=user_id,
                username=username,
                email=email,
                password_hash=password_hash,
                salt=salt,
                **profile_data
            )

            session.add(user)
            session.commit()
            session.refresh(user)

            logger.info(f"✅ 用户创建成功: {username} ({user.user_id})")
            return {
                "success": True,
                "message": "用户创建成功",
                "user_id": user.user_id
            }

        except IntegrityError as e:
            session.rollback()
            logger.error(f"❌ 用户创建失败（ IntegrityError）: {e}")
            return {"success": False, "message": "用户名或邮箱已存在", "user_id": None}
        except Exception as e:
            session.rollback()
            logger.error(f"❌ 用户创建失败: {e}")
            return {"success": False, "message": f"创建失败: {str(e)}", "user_id": None}
        finally:
            session.close()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.username == username).first()
            return user
        finally:
            session.close()

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据 user_id 获取用户"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            return user
        finally:
            session.close()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.email == email).first()
            return user
        finally:
            session.close()

    def verify_password(self, username: str, password_hash: str) -> Optional[User]:
        """验证用户密码（通过哈希匹配）"""
        session = self.get_session()
        try:
            user = session.query(User).filter(
                and_(User.username == username, User.password_hash == password_hash)
            ).first()
            return user
        finally:
            session.close()

    def update_user_last_login(self, user_id: str) -> bool:
        """更新用户最后登录时间"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.last_login = datetime.utcnow()
                user.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"❌ 更新登录时间失败: {e}")
            return False
        finally:
            session.close()

    def update_user_profile(self, user_id: str, **profile_data) -> bool:
        """更新用户资料"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                for key, value in profile_data.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                user.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"❌ 更新用户资料失败: {e}")
            return False
        finally:
            session.close()

    def update_user_password(self, user_id: str, password_hash: str) -> bool:
        """更新用户密码"""
        return self.update_user_profile(user_id, password_hash=password_hash)

    # ==================== 会话管理 ====================

    def create_conversation(
        self,
        user_id: str,
        title: str,
        trip_preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建新会话

        Args:
            user_id: 用户ID
            title: 会话标题
            trip_preferences: 旅行偏好字典

        Returns:
            Dict: {"success": bool, "message": str, "conversation_id": Optional[str]}
        """
        session = self.get_session()
        try:
            # 检查用户是否存在
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                return {"success": False, "message": "用户不存在", "conversation_id": None}

            # 检查配额（活跃会话数量）
            active_count = session.query(func.count(Conversation.conversation_id)).filter(
                and_(
                    Conversation.user_id == user_id,
                    Conversation.status == 'active'
                )
            ).scalar() or 0

            if active_count >= user.max_conversations:
                return {
                    "success": False,
                    "message": f"已达到最大会话数量限制（{user.max_conversations}个），请先归档或删除旧会话",
                    "conversation_id": None
                }

            # 创建会话
            import secrets
            conversation_id = f"conv_{secrets.token_hex(8)}"

            conversation = Conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                title=title,
                trip_preferences=trip_preferences,
                destination=trip_preferences.get('destination', ''),
                status='active'
            )

            # 更新用户统计信息
            user.total_plans_created += 1

            session.add(conversation)
            session.commit()
            session.refresh(conversation)

            logger.info(f"✅ 会话创建成功: {conversation_id}, 用户行程总数: {user.total_plans_created}")
            return {
                "success": True,
                "message": "会话创建成功",
                "conversation_id": conversation_id
            }

        except Exception as e:
            session.rollback()
            logger.error(f"❌ 会话创建失败: {e}")
            return {
                "success": False,
                "message": f"创建失败: {str(e)}",
                "conversation_id": None
            }
        finally:
            session.close()

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取会话"""
        session = self.get_session()
        try:
            conversation = session.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            ).first()
            return conversation
        finally:
            session.close()

    def list_conversations(
        self,
        user_id: str,
        status: Optional[Literal["active", "archived", "deleted"]] = "active",
        sort_by: str = "updated_at",
        order: Literal["asc", "desc"] = "desc",
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        列出用户的会话

        Args:
            user_id: 用户ID
            status: 会话状态
            sort_by: 排序字段
            order: 排序方向
            limit: 限制数量

        Returns:
            List[Dict]: 会话摘要列表
        """
        session = self.get_session()
        try:
            query = session.query(Conversation).filter(Conversation.user_id == user_id)

            # 状态过滤
            if status:
                query = query.filter(Conversation.status == status)

            # 排序
            sort_column = getattr(Conversation, sort_by, Conversation.updated_at)
            if order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)

            # 限制
            if limit:
                query = query.limit(limit)

            conversations = query.all()

            return [conv.to_summary_dict() for conv in conversations]

        finally:
            session.close()

    def delete_conversation(
        self,
        conversation_id: str,
        permanently: bool = False
    ) -> Dict[str, Any]:
        """
        删除会话

        Args:
            conversation_id: 会话ID
            permanently: 是否永久删除

        Returns:
            Dict: {"success": bool, "message": str}
        """
        session = self.get_session()
        try:
            conversation = session.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            ).first()

            if not conversation:
                return {"success": False, "message": "会话不存在"}

            if permanently:
                # 永久删除
                session.delete(conversation)
                session.commit()
                logger.info(f"✅ 永久删除会话: {conversation_id}")
                return {"success": True, "message": "会话已永久删除"}
            else:
                # 软删除
                conversation.status = 'deleted'
                conversation.updated_at = datetime.utcnow()
                session.commit()
                logger.info(f"✅ 标记删除会话: {conversation_id}")
                return {"success": True, "message": "会话已删除"}

        except Exception as e:
            session.rollback()
            logger.error(f"❌ 删除会话失败: {e}")
            return {"success": False, "message": f"删除失败: {str(e)}"}
        finally:
            session.close()

    def update_conversation_title(self, conversation_id: str, new_title: str) -> Dict[str, Any]:
        """更新会话标题"""
        session = self.get_session()
        try:
            conversation = session.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            ).first()

            if not conversation:
                return {"success": False, "message": "会话不存在"}

            old_title = conversation.title
            conversation.title = new_title
            conversation.updated_at = datetime.utcnow()
            session.commit()

            logger.info(f"✅ 会话标题已更新: {conversation_id} '{old_title}' -> '{new_title}'")
            return {"success": True, "message": "标题已更新"}

        except Exception as e:
            session.rollback()
            logger.error(f"❌ 更新会话标题失败: {e}")
            return {"success": False, "message": f"更新失败: {str(e)}"}
        finally:
            session.close()

    def archive_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """归档会话"""
        session = self.get_session()
        try:
            conversation = session.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            ).first()

            if not conversation:
                return {"success": False, "message": "会话不存在"}

            conversation.status = 'archived'
            conversation.updated_at = datetime.utcnow()
            session.commit()

            logger.info(f"✅ 归档会话: {conversation_id}")
            return {"success": True, "message": "会话已归档"}

        except Exception as e:
            session.rollback()
            logger.error(f"❌ 归档会话失败: {e}")
            return {"success": False, "message": f"归档失败: {str(e)}"}
        finally:
            session.close()

    def restore_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """恢复会话"""
        session = self.get_session()
        try:
            conversation = session.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            ).first()

            if not conversation:
                return {"success": False, "message": "会话不存在"}

            conversation.status = 'active'
            conversation.updated_at = datetime.utcnow()
            session.commit()

            logger.info(f"✅ 恢复会话: {conversation_id}")
            return {"success": True, "message": "会话已恢复"}

        except Exception as e:
            session.rollback()
            logger.error(f"❌ 恢复会话失败: {e}")
            return {"success": False, "message": f"恢复失败: {str(e)}"}
        finally:
            session.close()

    def search_conversations(self, user_id: str, keyword: str) -> List[Dict[str, Any]]:
        """搜索会话"""
        session = self.get_session()
        try:
            keyword_lower = f"%{keyword.lower()}%"

            conversations = session.query(Conversation).filter(
                and_(
                    Conversation.user_id == user_id,
                    or_(
                        func.lower(Conversation.title).like(keyword_lower),
                        func.lower(Conversation.destination).like(keyword_lower)
                    )
                )
            ).order_by(desc(Conversation.updated_at)).all()

            return [conv.to_summary_dict() for conv in conversations]

        finally:
            session.close()

    def get_conversation_count(self, user_id: str, status: str = "active") -> int:
        """获取用户会话数量"""
        session = self.get_session()
        try:
            count = session.query(func.count(Conversation.conversation_id)).filter(
                and_(
                    Conversation.user_id == user_id,
                    Conversation.status == status
                )
            ).scalar() or 0
            return count
        finally:
            session.close()

    def get_quota_info(self, user_id: str) -> Dict[str, Any]:
        """获取用户配额信息"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                return {"error": "用户不存在"}

            active_count = self.get_conversation_count(user_id, "active")
            archived_count = self.get_conversation_count(user_id, "archived")

            return {
                "current": active_count,
                "max": user.max_conversations,
                "archived": archived_count,
                "can_create": active_count < user.max_conversations
            }
        finally:
            session.close()

    # ==================== 消息管理 ====================

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        添加消息到会话

        Args:
            conversation_id: 会话ID
            role: 角色 (user/assistant/system)
            content: 消息内容
            metadata: 元数据

        Returns:
            bool: 是否成功
        """
        session = self.get_session()
        try:
            conversation = session.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            ).first()

            if not conversation:
                logger.error(f"❌ 会话不存在: {conversation_id}")
                return False

            # 创建消息
            message = Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                meta_data=metadata
            )

            session.add(message)

            # 更新会话统计
            conversation.message_count += 1
            conversation.updated_at = datetime.utcnow()

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"❌ 添加消息失败: {e}")
            return False
        finally:
            session.close()

    def get_conversation_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        获取会话消息（用于 LLM 上下文）

        Args:
            conversation_id: 会话ID
            limit: 最大消息数

        Returns:
            List[Dict]: [{"role": "user", "content": "..."}, ...]
        """
        session = self.get_session()
        try:
            query = session.query(Message).filter(
                Message.conversation_id == conversation_id
            ).order_by(Message.timestamp)

            if limit:
                query = query.limit(limit)

            messages = query.all()

            return [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]

        finally:
            session.close()

    # ==================== 资源管理 ====================

    def add_resource(
        self,
        conversation_id: str,
        resource_type: str,
        file_path: str,
        file_type: str,
        description: Optional[str] = None
    ) -> bool:
        """
        添加资源到会话

        Args:
            conversation_id: 会话ID
            resource_type: 资源类型 (map_files/generated_files/images)
            file_path: 文件路径
            file_type: 文件类型 (map/excel/html/image)
            description: 描述

        Returns:
            bool: 是否成功
        """
        session = self.get_session()
        try:
            conversation = session.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            ).first()

            if not conversation:
                logger.error(f"❌ 会话不存在: {conversation_id}")
                return False

            # 创建资源
            resource = Resource(
                conversation_id=conversation_id,
                resource_type=resource_type,
                file_path=file_path,
                file_type=file_type,
                description=description
            )

            session.add(resource)

            # 更新会话统计
            if resource_type == 'map_files':
                conversation.has_map = True
            elif resource_type in ('generated_files', 'images'):
                conversation.has_files = True

            conversation.updated_at = datetime.utcnow()

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"❌ 添加资源失败: {e}")
            return False
        finally:
            session.close()

    def get_conversation_resources(self, conversation_id: str) -> Dict[str, List[Dict]]:
        """获取会话资源"""
        session = self.get_session()
        try:
            resources = session.query(Resource).filter(
                Resource.conversation_id == conversation_id
            ).all()

            result = {
                "map_files": [],
                "generated_files": [],
                "images": []
            }

            for resource in resources:
                result[resource.resource_type].append(resource.to_dict())

            return result

        finally:
            session.close()

    # ==================== 数据清理 ====================

    def purge_deleted_conversations(self, max_age_days: int = 7) -> int:
        """
        永久删除超过指定天数的已删除会话（回收站自动清理）

        Args:
            max_age_days: 最大保留天数（默认7天）

        Returns:
            int: 永久删除的会话数量
        """
        session = self.get_session()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)

            # 查找超过保留期的已删除会话
            old_deleted_convs = session.query(Conversation).filter(
                and_(
                    Conversation.status == 'deleted',
                    Conversation.updated_at < cutoff_date
                )
            ).all()

            count = 0
            for conv in old_deleted_convs:
                session.delete(conv)
                count += 1

            session.commit()

            if count > 0:
                logger.info(f"🗑️ 永久删除了 {count} 个超过{max_age_days}天的已删除会话")

            return count

        except Exception as e:
            session.rollback()
            logger.error(f"❌ 永久删除旧会话失败: {e}")
            return 0
        finally:
            session.close()
