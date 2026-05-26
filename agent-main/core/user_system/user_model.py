"""
用户数据模型类
定义用户的基本信息、认证和统计
"""
import hashlib
import secrets
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field, validator, EmailStr


class UserProfile(BaseModel):
    """用户个人资料"""
    nickname: str = "旅行者"
    avatar_url: Optional[str] = None
    gender: Optional[str] = None  # male/female/other
    birth_year: Optional[int] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    school: Optional[str] = None


class UserQuota(BaseModel):
    """用户配额限制"""
    max_conversations: int = 10  # 免费用户最多10个活跃会话
    max_archived_conversations: int = 50
    current_conversation_count: int = 0


class UserStatistics(BaseModel):
    """用户统计数据"""
    total_plans_created: int = 0
    total_destinations: int = 0
    favorite_destinations: List[str] = []
    total_budget_spent: float = 0.0


class UserSystem(BaseModel):
    """用户系统信息"""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_login: str = Field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True
    is_verified: bool = False  # 学生身份验证
    subscription_tier: str = "free"  # free/premium


class UserModel(BaseModel):
    """
    用户数据模型

    职责：
    - 定义用户数据结构
    - 密码加密和验证
    - 数据序列化/反序列化
    """

    # ========== 基本信息 ==========
    user_id: str
    username: str
    email: Optional[str] = None
    password_hash: str
    salt: str

    # ========== 个人资料 ==========
    profile: UserProfile = Field(default_factory=UserProfile)

    # ========== 系统信息 ==========
    system: UserSystem = Field(default_factory=UserSystem)

    # ========== 配额限制 ==========
    quota: UserQuota = Field(default_factory=UserQuota)

    # ========== 统计数据 ==========
    statistics: UserStatistics = Field(default_factory=UserStatistics)

    @validator('username')
    def validate_username(cls, v):
        """验证用户名格式"""
        if not v or len(v) < 3 or len(v) > 20:
            raise ValueError("用户名长度必须在3-20个字符之间")
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError("用户名只能包含字母、数字、下划线和连字符")
        return v

    @validator('email')
    def validate_email(cls, v):
        """验证邮箱格式（如果提供）"""
        if v and '@' not in v:
            raise ValueError("邮箱格式不正确")
        return v

    @staticmethod
    def generate_salt() -> str:
        """生成随机盐值"""
        return secrets.token_hex(16)

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        """
        使用 SHA-256 + 盐值加密密码

        注意：生产环境建议使用 bcrypt 或 argon2
        这里使用 SHA-256 是为了简化依赖
        """
        password_salt = (password + salt).encode('utf-8')
        return hashlib.sha256(password_salt).hexdigest()

    def verify_password(self, password: str) -> bool:
        """验证密码"""
        password_hash = self.hash_password(password, self.salt)
        return password_hash == self.password_hash

    def update_last_login(self):
        """更新最后登录时间"""
        self.system.last_login = datetime.now().isoformat()
        self.system.updated_at = datetime.now().isoformat()

    def update_profile(self, **kwargs):
        """更新个人资料"""
        profile_data = self.profile.dict()
        profile_data.update(kwargs)
        self.profile = UserProfile(**profile_data)
        self.system.updated_at = datetime.now().isoformat()

    def increment_plan_count(self):
        """增加计划创建数"""
        self.statistics.total_plans_created += 1
        self.system.updated_at = datetime.now().isoformat()

    def add_destination(self, destination: str):
        """添加到常去目的地"""
        if destination not in self.statistics.favorite_destinations:
            self.statistics.favorite_destinations.append(destination)
            self.statistics.total_destinations = len(self.statistics.favorite_destinations)
        self.system.updated_at = datetime.now().isoformat()

    def add_budget_spent(self, amount: float):
        """累计花费"""
        self.statistics.total_budget_spent += amount
        self.system.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "password_hash": self.password_hash,
            "salt": self.salt,
            "profile": self.profile.dict(),
            "system": self.system.dict(),
            "quota": self.quota.dict(),
            "statistics": self.statistics.dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserModel':
        """从字典创建实例"""
        return cls(
            user_id=data.get("user_id"),
            username=data.get("username"),
            email=data.get("email"),
            password_hash=data.get("password_hash"),
            salt=data.get("salt"),
            profile=UserProfile(**data.get("profile", {})),
            system=UserSystem(**data.get("system", {})),
            quota=UserQuota(**data.get("quota", {})),
            statistics=UserStatistics(**data.get("statistics", {}))
        )

    @classmethod
    def create_new(cls, username: str, password: str, email: Optional[str] = None, **profile_data) -> 'UserModel':
        """
        创建新用户

        Args:
            username: 用户名
            password: 明文密码
            email: 邮箱（可选）
            **profile_data: 其他个人资料

        Returns:
            UserModel: 新用户实例
        """
        # 生成用户ID
        user_id = f"user_{secrets.token_hex(8)}"

        # 生成盐值和密码哈希
        salt = cls.generate_salt()
        password_hash = cls.hash_password(password, salt)

        # 创建个人资料
        profile = UserProfile(**profile_data)

        return cls(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            salt=salt,
            profile=profile
        )

    def __repr__(self):
        return f"<UserModel(user_id={self.user_id}, username={self.username})>"
