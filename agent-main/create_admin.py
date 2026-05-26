"""
创建管理员用户脚本
==================
用于创建管理员账户，支持命令行参数和交互式输入

使用方法：
    # 交互式创建
    python create_admin.py

    # 命令行参数创建
    python create_admin.py --username admin --password yourpassword --role super_admin

    # 快速创建默认管理员
    python create_admin.py --quick
"""
import os
import sys
import argparse
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 中国时区 UTC+8
CHINA_TIMEZONE = timezone(timedelta(hours=8))

def get_local_now():
    """获取中国本地时间"""
    return datetime.now(CHINA_TIMEZONE).replace(tzinfo=None)

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv(project_root / '.env')

from passlib.context import CryptContext

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_database_url() -> str:
    """获取数据库连接字符串"""
    return os.getenv('DATABASE_URL', 'sqlite:///./data/trip_planner.db')


def init_database():
    """初始化数据库连接"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    database_url = get_database_url()
    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {}
    )

    # 创建表
    from core.database.models import Base
    from core.database.admin_models import Base as AdminBase

    Base.metadata.create_all(bind=engine, checkfirst=True)
    AdminBase.metadata.create_all(bind=engine, checkfirst=True)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal


def create_admin_user(
    username: str,
    password: str,
    email: str = None,
    role: str = 'admin',
    nickname: str = None
) -> dict:
    """
    创建管理员用户

    Args:
        username: 用户名
        password: 密码
        email: 邮箱（可选）
        role: 角色 (super_admin, admin, support)
        nickname: 昵称（可选）

    Returns:
        dict: {"success": bool, "message": str, "user_id": str}
    """
    SessionLocal = init_database()
    session = SessionLocal()

    try:
        from core.database.models import User
        from core.database.admin_models import AdminUser

        # 1. 检查用户名是否已存在
        existing_user = session.query(User).filter(User.username == username).first()
        if existing_user:
            return {"success": False, "message": f"用户名 '{username}' 已存在", "user_id": None}

        # 2. 检查邮箱是否已存在
        if email:
            existing_email = session.query(User).filter(User.email == email).first()
            if existing_email:
                return {"success": False, "message": f"邮箱 '{email}' 已被注册", "user_id": None}

        # 3. 检查是否已经是管理员
        existing_admin = session.query(AdminUser).filter(AdminUser.user_id == username).first()
        if existing_admin:
            return {"success": False, "message": f"用户 '{username}' 已经是管理员", "user_id": None}

        # 4. 创建用户账户
        user_id = f"user_{secrets.token_hex(8)}"
        password_hash = pwd_context.hash(password)

        user = User(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            salt="",  # BCrypt 不需要单独的盐
            nickname=nickname or username,
            is_active=True,
            is_verified=True,  # 管理员默认已验证
            subscription_tier='admin',  # 管理员订阅级别
            max_conversations=999,  # 管理员无限制
            max_archived_conversations=999
        )

        session.add(user)

        # 5. 创建管理员记录
        admin_user = AdminUser(
            user_id=user_id,
            role=role,
            is_active=True,
            created_at=get_local_now()
        )

        session.add(admin_user)
        session.commit()

        return {
            "success": True,
            "message": f"管理员用户创建成功！",
            "user_id": user_id,
            "username": username,
            "role": role
        }

    except Exception as e:
        session.rollback()
        return {"success": False, "message": f"创建失败: {str(e)}", "user_id": None}
    finally:
        session.close()


def list_admin_users():
    """列出所有管理员用户"""
    SessionLocal = init_database()
    session = SessionLocal()

    try:
        from core.database.models import User
        from core.database.admin_models import AdminUser

        admins = session.query(AdminUser).all()

        if not admins:
            print("\n📭 当前没有管理员用户")
            return

        print("\n📋 管理员用户列表:")
        print("-" * 60)
        print(f"{'用户ID':<20} {'用户名':<15} {'角色':<15} {'状态':<10}")
        print("-" * 60)

        for admin in admins:
            user = session.query(User).filter(User.user_id == admin.user_id).first()
            username = user.username if user else "未知"
            status = "✅ 活跃" if admin.is_active else "❌ 禁用"
            print(f"{admin.user_id:<20} {username:<15} {admin.role:<15} {status:<10}")

        print("-" * 60)

    finally:
        session.close()


def interactive_create():
    """交互式创建管理员"""
    print("\n" + "=" * 50)
    print("🔧 创建管理员用户")
    print("=" * 50)

    # 用户名
    while True:
        username = input("\n请输入用户名 (3-20字符): ").strip()
        if 3 <= len(username) <= 20:
            if username.replace('_', '').replace('-', '').isalnum():
                break
            else:
                print("❌ 用户名只能包含字母、数字、下划线和连字符")
        else:
            print("❌ 用户名长度必须在3-20个字符之间")

    # 密码
    while True:
        password = input("请输入密码 (至少6字符): ").strip()
        if len(password) >= 6:
            confirm = input("请确认密码: ").strip()
            if password == confirm:
                break
            else:
                print("❌ 两次密码不一致")
        else:
            print("❌ 密码长度至少6个字符")

    # 邮箱（可选）
    email = input("请输入邮箱 (可选，直接回车跳过): ").strip() or None

    # 角色
    print("\n可选角色:")
    print("  1. super_admin - 超级管理员（最高权限）")
    print("  2. admin       - 普通管理员")
    print("  3. support     - 客服支持")

    role_choice = input("请选择角色 [1-3，默认2]: ").strip() or "2"
    role_map = {"1": "super_admin", "2": "admin", "3": "support"}
    role = role_map.get(role_choice, "admin")

    # 昵称
    nickname = input("请输入昵称 (可选，直接回车跳过): ").strip() or None

    # 确认创建
    print("\n" + "-" * 40)
    print(f"用户名: {username}")
    print(f"邮箱:   {email or '未设置'}")
    print(f"角色:   {role}")
    print(f"昵称:   {nickname or username}")
    print("-" * 40)

    confirm = input("\n确认创建? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("❌ 已取消")
        return

    # 创建
    result = create_admin_user(username, password, email, role, nickname)

    if result["success"]:
        print(f"\n✅ {result['message']}")
        print(f"   用户ID: {result['user_id']}")
        print(f"   用户名: {result['username']}")
        print(f"   角色:   {result['role']}")
    else:
        print(f"\n❌ {result['message']}")


def main():
    parser = argparse.ArgumentParser(description='创建管理员用户')
    parser.add_argument('--username', '-u', help='用户名')
    parser.add_argument('--password', '-p', help='密码')
    parser.add_argument('--email', '-e', help='邮箱')
    parser.add_argument('--role', '-r', choices=['super_admin', 'admin', 'support'],
                       default='admin', help='角色 (默认: admin)')
    parser.add_argument('--nickname', '-n', help='昵称')
    parser.add_argument('--quick', '-q', action='store_true',
                       help='快速创建默认管理员 (admin/admin123)')
    parser.add_argument('--list', '-l', action='store_true',
                       help='列出所有管理员用户')

    args = parser.parse_args()

    # 列出管理员
    if args.list:
        list_admin_users()
        return

    # 快速创建
    if args.quick:
        print("\n🚀 快速创建默认管理员...")
        result = create_admin_user(
            username="admin",
            password="admin123",
            email="admin@example.com",
            role="super_admin",
            nickname="超级管理员"
        )

        if result["success"]:
            print(f"✅ {result['message']}")
            print(f"   用户名: admin")
            print(f"   密码:   admin123")
            print(f"   角色:   super_admin")
            print("\n⚠️  请登录后立即修改密码！")
        else:
            print(f"❌ {result['message']}")
        return

    # 命令行参数创建
    if args.username and args.password:
        result = create_admin_user(
            username=args.username,
            password=args.password,
            email=args.email,
            role=args.role,
            nickname=args.nickname
        )

        if result["success"]:
            print(f"✅ {result['message']}")
            print(f"   用户ID: {result['user_id']}")
        else:
            print(f"❌ {result['message']}")
        return

    # 交互式创建
    interactive_create()


if __name__ == "__main__":
    main()
