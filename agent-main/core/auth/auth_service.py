"""
用户认证服务
提供用户注册、登录、JWT 令牌管理等功能
"""
import os
import secrets
import jwt
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from passlib.context import CryptContext
import logging

logger = logging.getLogger(__name__)


# JWT 配置
def _load_secret_key() -> str:
    """
    加载 JWT 密钥

    优先级：
    1. 环境变量 JWT_SECRET_KEY
    2. 项目根目录的 .jwt_secret_key 文件
    3. 生成新密钥并保存到文件

    Returns:
        str: JWT 密钥
    """
    # 1. 尝试从环境变量读取
    secret_key = os.getenv('JWT_SECRET_KEY', None)
    if secret_key:
        logger.info("✅ JWT 密钥从环境变量加载")
        return secret_key

    # 2. 尝试从文件读取
    key_file = Path(__file__).parent.parent / ".jwt_secret_key"
    if key_file.exists():
        try:
            secret_key = key_file.read_text().strip()
            if secret_key and len(secret_key) >= 32:
                logger.info(f"✅ JWT 密钥从文件加载: {key_file}")
                return secret_key
        except Exception as e:
            logger.warning(f"⚠️ 读取 JWT 密钥文件失败: {e}")

    # 3. 生成新密钥并保存
    secret_key = secrets.token_hex(32)
    try:
        key_file.write_text(secret_key)
        logger.info(f"⚠️ 警告: JWT_SECRET_KEY 未设置，已生成并保存到 {key_file}")
        logger.info("⚠️ 建议: 在生产环境中设置 JWT_SECRET_KEY 环境变量")
    except Exception as e:
        logger.warning(f"⚠️ 无法保存 JWT 密钥到文件: {e}")

    return secret_key


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 天


# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """
    用户认证服务

    功能：
    - 密码加密和验证
    - JWT 令牌生成和验证
    - 用户注册和登录
    """

    def __init__(self, db_repository):
        """
        初始化认证服务

        Args:
            db_repository: DatabaseRepository 实例
        """
        self.db = db_repository

    @staticmethod
    def hash_password(password: str) -> str:
        """
        使用 BCrypt 加密密码

        Args:
            password: 明文密码

        Returns:
            str: 加密后的密码
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        验证密码

        Args:
            plain_password: 明文密码
            hashed_password: 加密后的密码

        Returns:
            bool: 是否匹配
        """
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        创建 JWT 访问令牌

        Args:
            data: 要编码的数据（通常包含 user_id 和 username）
            expires_delta: 过期时间增量

        Returns:
            str: JWT 令牌
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow()
        })

        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    def decode_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        解码 JWT 令牌

        Args:
            token: JWT 令牌

        Returns:
            Optional[Dict]: 解码后的数据，失败返回 None
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("⚠️ JWT 令牌已过期")
            return None
        except jwt.JWTError as e:
            logger.error(f"❌ JWT 令牌解码失败: {e}")
            return None

    def register(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        **profile_data
    ) -> Dict[str, Any]:
        """
        用户注册

        Args:
            username: 用户名
            password: 明文密码
            email: 邮箱（可选）
            **profile_data: 其他个人资料

        Returns:
            Dict: {
                "success": bool,
                "message": str,
                "user_id": Optional[str],
                "access_token": Optional[str]
            }
        """
        # 验证用户名格式
        if not username or len(username) < 3 or len(username) > 20:
            return {
                "success": False,
                "message": "用户名长度必须在3-20个字符之间",
                "user_id": None,
                "access_token": None
            }

        if not username.replace('_', '').replace('-', '').isalnum():
            return {
                "success": False,
                "message": "用户名只能包含字母、数字、下划线和连字符",
                "user_id": None,
                "access_token": None
            }

        # 验证密码强度
        if not password or len(password) < 6:
            return {
                "success": False,
                "message": "密码长度至少6个字符",
                "user_id": None,
                "access_token": None
            }

        # 验证邮箱格式
        if email and '@' not in email:
            return {
                "success": False,
                "message": "邮箱格式不正确",
                "user_id": None,
                "access_token": None
            }

        # 加密密码
        password_hash = self.hash_password(password)

        # 创建用户
        result = self.db.create_user(
            username=username,
            password_hash=password_hash,
            salt="",  # BCrypt 不需要单独的盐
            email=email,
            **profile_data
        )

        if not result["success"]:
            return {
                "success": False,
                "message": result["message"],
                "user_id": None,
                "access_token": None
            }

        user_id = result["user_id"]

        # 生成访问令牌
        access_token = self.create_access_token(
            data={"sub": user_id, "username": username}
        )

        logger.info(f"✅ 用户注册成功: {username} ({user_id})")

        return {
            "success": True,
            "message": "注册成功",
            "user_id": user_id,
            "access_token": access_token
        }

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户登录

        Args:
            username: 用户名或邮箱
            password: 明文密码

        Returns:
            Dict: {
                "success": bool,
                "message": str,
                "user_id": Optional[str],
                "access_token": Optional[str],
                "user": Optional[Dict]
            }
        """
        # 查找用户（支持用户名或邮箱登录）
        user = self.db.get_user_by_username(username)
        if not user:
            user = self.db.get_user_by_email(username)

        if not user:
            return {
                "success": False,
                "message": "用户名或密码错误",
                "user_id": None,
                "access_token": None,
                "user": None
            }

        # 验证密码
        if not self.verify_password(password, user.password_hash):
            return {
                "success": False,
                "message": "用户名或密码错误",
                "user_id": None,
                "access_token": None,
                "user": None
            }

        # 检查账户状态
        if not user.is_active:
            return {
                "success": False,
                "message": "账户已被禁用",
                "user_id": None,
                "access_token": None,
                "user": None
            }

        # 更新最后登录时间
        self.db.update_user_last_login(user.user_id)

        # 生成访问令牌
        access_token = self.create_access_token(
            data={"sub": user.user_id, "username": user.username}
        )

        logger.info(f"✅ 用户登录成功: {user.username} ({user.user_id})")

        return {
            "success": True,
            "message": "登录成功",
            "user_id": user.user_id,
            "access_token": access_token,
            "user": user.to_dict()
        }

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证 JWT 令牌并返回用户信息

        Args:
            token: JWT 令牌

        Returns:
            Optional[Dict]: {"user_id": str, "username": str} 或 None
        """
        payload = self.decode_access_token(token)
        if not payload:
            return None

        user_id = payload.get("sub")
        username = payload.get("username")

        if not user_id:
            return None

        # 验证用户是否存在且活跃
        user = self.db.get_user_by_id(user_id)
        if not user or not user.is_active:
            return None

        return {
            "user_id": user_id,
            "username": username
        }

    def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """
        获取当前登录用户的信息

        Args:
            token: JWT 令牌

        Returns:
            Optional[Dict]: 用户完整信息
        """
        auth_data = self.verify_token(token)
        if not auth_data:
            return None

        user = self.db.get_user_by_id(auth_data["user_id"])
        if user:
            return user.to_dict()
        return None
