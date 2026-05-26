"""
SQLAlchemy 数据库模型
基于现有的 UserModel 和 ConversationModel 进行适配
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text,
    ForeignKey, DECIMAL, JSON, Index, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship, backref
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """所有模型的基类"""
    pass


# ==================== 用户表 ====================

class User(Base):
    """用户表 - 对应 UserModel"""
    __tablename__ = 'users'

    # ========== 基本信息 ==========
    user_id = Column(String(64), primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, index=True)
    password_hash = Column(String(128), nullable=False)
    salt = Column(String(64), nullable=False)

    # ========== 个人资料 ==========
    nickname = Column(String(50), default='旅行者')
    avatar_url = Column(Text)
    gender = Column(String(10))  # male/female/other
    birth_year = Column(Integer)
    location = Column(String(100))
    bio = Column(Text)
    school = Column(String(100))

    # ========== 系统信息 ==========
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # 学生身份验证
    subscription_tier = Column(String(20), default='free')  # free/premium

    # ========== 配额 ==========
    max_conversations = Column(Integer, default=10)
    max_archived_conversations = Column(Integer, default=50)

    # ========== 统计 ==========
    total_plans_created = Column(Integer, default=0)
    total_destinations = Column(Integer, default=0)
    favorite_destinations = Column(JSON, default=list)
    total_budget_spent = Column(DECIMAL(10, 2), default=0.0)

    # ========== 关系 ==========
    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(Conversation.updated_at)"
    )

    def __repr__(self):
        return f"<User(user_id={self.user_id}, username={self.username})>"

    def to_dict(self) -> dict:
        """转换为字典（不包含敏感信息）"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "nickname": self.nickname,
            "avatar_url": self.avatar_url,
            "gender": self.gender,
            "birth_year": self.birth_year,
            "location": self.location,
            "bio": self.bio,
            "school": self.school,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "subscription_tier": self.subscription_tier,
            "max_conversations": self.max_conversations,
            "max_archived_conversations": self.max_archived_conversations,
            "total_plans_created": self.total_plans_created,
            "total_destinations": self.total_destinations,
            "favorite_destinations": self.favorite_destinations or [],
            "total_budget_spent": float(self.total_budget_spent) if self.total_budget_spent else 0.0,
        }

    def to_user_model(self) -> 'UserModel':
        """转换为原有的 UserModel（向后兼容）"""
        from core.user_system.user_model import UserModel, UserProfile, UserQuota, UserStatistics, UserSystem
        return UserModel(
            user_id=self.user_id,
            username=self.username,
            email=self.email,
            password_hash=self.password_hash,
            salt=self.salt,
            profile=UserProfile(
                nickname=self.nickname,
                avatar_url=self.avatar_url,
                gender=self.gender,
                birth_year=self.birth_year,
                location=self.location,
                bio=self.bio,
                school=self.school
            ),
            system=UserSystem(
                created_at=self.created_at.isoformat() if self.created_at else None,
                updated_at=self.updated_at.isoformat() if self.updated_at else None,
                last_login=self.last_login.isoformat() if self.last_login else None,
                is_active=self.is_active,
                is_verified=self.is_verified,
                subscription_tier=self.subscription_tier
            ),
            quota=UserQuota(
                max_conversations=self.max_conversations,
                max_archived_conversations=self.max_archived_conversations,
                current_conversation_count=len([c for c in self.conversations if c.status == 'active'])
            ),
            statistics=UserStatistics(
                total_plans_created=self.total_plans_created,
                total_destinations=self.total_destinations,
                favorite_destinations=self.favorite_destinations or [],
                total_budget_spent=float(self.total_budget_spent) if self.total_budget_spent else 0.0
            )
        )

    @classmethod
    def from_user_model(cls, user_model: 'UserModel') -> 'User':
        """从 UserModel 创建数据库实例"""
        return cls(
            user_id=user_model.user_id,
            username=user_model.username,
            email=user_model.email,
            password_hash=user_model.password_hash,
            salt=user_model.salt,
            nickname=user_model.profile.nickname,
            avatar_url=user_model.profile.avatar_url,
            gender=user_model.profile.gender,
            birth_year=user_model.profile.birth_year,
            location=user_model.profile.location,
            bio=user_model.profile.bio,
            school=user_model.profile.school,
            created_at=datetime.fromisoformat(user_model.system.created_at) if user_model.system.created_at else None,
            updated_at=datetime.fromisoformat(user_model.system.updated_at) if user_model.system.updated_at else None,
            last_login=datetime.fromisoformat(user_model.system.last_login) if user_model.system.last_login else None,
            is_active=user_model.system.is_active,
            is_verified=user_model.system.is_verified,
            subscription_tier=user_model.system.subscription_tier,
            max_conversations=user_model.quota.max_conversations,
            max_archived_conversations=user_model.quota.max_archived_conversations,
            total_plans_created=user_model.statistics.total_plans_created,
            total_destinations=user_model.statistics.total_destinations,
            favorite_destinations=user_model.statistics.favorite_destinations,
            total_budget_spent=user_model.statistics.total_budget_spent
        )


# ==================== 会话表 ====================

class Conversation(Base):
    """会话表 - 对应 ConversationModel"""
    __tablename__ = 'conversations'

    # ========== 基本信息 ==========
    conversation_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    title = Column(String(200), nullable=False)

    # ========== 旅行偏好 (JSON 存储) ==========
    trip_preferences = Column(JSON, nullable=False)

    # ========== 元数据 ==========
    destination = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(String(20), default='active')  # active/archived/deleted
    is_pinned = Column(Boolean, default=False)
    tags = Column(JSON, default=list)

    # ========== 统计 ==========
    message_count = Column(Integer, default=0)
    has_map = Column(Boolean, default=False)
    has_files = Column(Boolean, default=False)

    # ========== 关系 ==========
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.timestamp"
    )
    resources = relationship(
        "Resource",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )

    # ========== 索引 ==========
    __table_args__ = (
        Index('idx_conversations_user_id', 'user_id'),
        Index('idx_conversations_status', 'status'),
        Index('idx_conversations_updated_at', 'updated_at'),
        CheckConstraint("status IN ('active', 'archived', 'deleted')", name='check_status'),
    )

    def __repr__(self):
        return f"<Conversation(id={self.conversation_id}, title={self.title})>"

    def to_dict(self, include_messages: bool = False, include_resources: bool = False) -> dict:
        """转换为字典"""
        result = {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "title": self.title,
            "trip_preferences": self.trip_preferences,
            "destination": self.destination,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "status": self.status,
            "is_pinned": self.is_pinned,
            "tags": self.tags or [],
            "message_count": self.message_count,
            "has_map": self.has_map,
            "has_files": self.has_files,
        }

        if include_messages:
            result["messages"] = [msg.to_dict() for msg in self.messages]

        if include_resources:
            result["resources"] = {
                "map_files": [r.to_dict() for r in self.resources if r.resource_type == 'map_files'],
                "generated_files": [r.to_dict() for r in self.resources if r.resource_type == 'generated_files'],
                "images": [r.to_dict() for r in self.resources if r.resource_type == 'images'],
            }

        return result

    def to_conversation_model(self) -> 'ConversationModel':
        """转换为原有的 ConversationModel（向后兼容）"""
        from core.user_system.conversation_model import (
            ConversationModel, TripPreferences, ConversationMetadata,
            MessageModel, ResourceFile
        )

        # 解析 trip_preferences
        prefs_data = self.trip_preferences if isinstance(self.trip_preferences, dict) else {}
        trip_prefs = TripPreferences(**prefs_data)

        # 解析消息
        messages = [msg.to_message_model() for msg in self.messages]

        # 解析资源
        resources = {
            "map_files": [r.to_resource_file() for r in self.resources if r.resource_type == 'map_files'],
            "generated_files": [r.to_resource_file() for r in self.resources if r.resource_type == 'generated_files'],
            "images": [r.to_resource_file() for r in self.resources if r.resource_type == 'images'],
        }

        # 元数据
        metadata = ConversationMetadata(
            created_at=self.created_at.isoformat() if self.created_at else None,
            updated_at=self.updated_at.isoformat() if self.updated_at else None,
            status=self.status,
            is_pinned=self.is_pinned,
            tags=self.tags or []
        )

        return ConversationModel(
            conversation_id=self.conversation_id,
            user_id=self.user_id,
            title=self.title,
            trip_preferences=trip_prefs,
            messages=messages,
            resources=resources,
            metadata=metadata
        )

    def to_summary_dict(self) -> dict:
        """转换为摘要字典（用于列表展示）"""
        return {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "destination": self.destination,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "status": self.status,
            "message_count": self.message_count,
            "has_map": self.has_map,
            "has_files": self.has_files,
            "is_pinned": self.is_pinned,
            "tags": self.tags or []
        }


# ==================== 消息表 ====================

class Message(Base):
    """消息表"""
    __tablename__ = 'messages'

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(64), ForeignKey('conversations.conversation_id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20), nullable=False)  # user/assistant/system
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    meta_data = Column(JSON)  # {"model_used": "...", "tools_used": [...], ...}

    # ========== 关系 ==========
    conversation = relationship("Conversation", back_populates="messages")

    # ========== 索引 ==========
    __table_args__ = (
        Index('idx_messages_conversation_id', 'conversation_id'),
        Index('idx_messages_timestamp', 'timestamp'),
        CheckConstraint("role IN ('user', 'assistant', 'system')", name='check_role'),
    )

    def __repr__(self):
        return f"<Message(id={self.message_id}, role={self.role})>"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.meta_data
        }

    def to_message_model(self) -> 'MessageModel':
        """转换为原有的 MessageModel（向后兼容）"""
        from core.user_system.conversation_model import MessageModel, MessageMetadata
        return MessageModel(
            role=self.role,
            content=self.content,
            timestamp=self.timestamp.isoformat() if self.timestamp else None,
            metadata=MessageMetadata(**self.meta_data) if self.meta_data else None
        )


# ==================== 资源表 ====================

class Resource(Base):
    """资源表"""
    __tablename__ = 'resources'

    resource_id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(64), ForeignKey('conversations.conversation_id', ondelete='CASCADE'), nullable=False)
    resource_type = Column(String(50), nullable=False)  # map_files/generated_files/images
    file_path = Column(Text, nullable=False)
    file_type = Column(String(20), nullable=False)  # map/excel/html/image
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ========== 关系 ==========
    conversation = relationship("Conversation", back_populates="resources")

    # ========== 索引 ==========
    __table_args__ = (
        Index('idx_resources_conversation_id', 'conversation_id'),
        Index('idx_resources_type', 'resource_type'),
        CheckConstraint("resource_type IN ('map_files', 'generated_files', 'images')", name='check_resource_type'),
    )

    def __repr__(self):
        return f"<Resource(id={self.resource_id}, type={self.resource_type})>"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "resource_id": self.resource_id,
            "conversation_id": self.conversation_id,
            "resource_type": self.resource_type,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def to_resource_file(self) -> 'ResourceFile':
        """转换为原有的 ResourceFile（向后兼容）"""
        from core.user_system.conversation_model import ResourceFile
        return ResourceFile(
            file_path=self.file_path,
            file_type=self.file_type,
            description=self.description
        )
