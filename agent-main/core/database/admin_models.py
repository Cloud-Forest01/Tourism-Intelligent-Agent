"""
管理员系统数据库模型
===================
扩展原有数据库，添加管理员相关表
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone, timedelta

# 中国时区 UTC+8
CHINA_TIMEZONE = timezone(timedelta(hours=8))

def get_local_now():
    """获取中国本地时间"""
    return datetime.now(CHINA_TIMEZONE).replace(tzinfo=None)

Base = declarative_base()


class AdminUser(Base):
    """管理员用户表"""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), unique=True, nullable=False, index=True)
    role = Column(String(20), default='admin', nullable=False)  # super_admin, admin, support
    created_at = Column(DateTime, default=get_local_now)
    last_login_at = Column(DateTime)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<AdminUser(id={self.id}, user_id={self.user_id}, role={self.role})>"


class AuditLog(Base):
    """审计日志表 - 记录所有管理员操作"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_user_id = Column(String(100), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # login, delete_user, ban_user, etc.
    resource_type = Column(String(50))  # user, session, config, etc.
    resource_id = Column(String(100))
    details = Column(Text)
    ip_address = Column(String(50))
    timestamp = Column(DateTime, default=get_local_now, index=True)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, admin={self.admin_user_id})>"


class SystemConfig(Base):
    """系统配置表 - 存储系统参数"""
    __tablename__ = "system_configs"

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    description = Column(String(255))
    category = Column(String(50))  # api, model, system, etc.
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)
    updated_by = Column(String(100))

    def __repr__(self):
        return f"<SystemConfig(key={self.key}, value={self.value})>"


class SystemAlert(Base):
    """系统告警表"""
    __tablename__ = "system_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_type = Column(String(50), nullable=False)  # cpu_high, memory_high, api_error
    severity = Column(String(20), nullable=False)  # info, warning, error, critical
    message = Column(Text, nullable=False)
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=get_local_now, index=True)

    def __repr__(self):
        return f"<SystemAlert(id={self.id}, type={self.alert_type}, severity={self.severity})>"


# 创建所有表的函数
def create_admin_tables(engine):
    """创建管理员相关表"""
    Base.metadata.create_all(engine, checkfirst=True)
    print("✅ 管理员数据库表创建成功")
