"""
Alembic 迁移环境配置
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入 Base 和模型
from core.database.models import Base

# 导入配置
from config import Config

# this is the Alembic Config object
config = context.config

# 设置数据库 URL（从环境变量或配置文件）
database_url = os.getenv('DATABASE_URL', 'sqlite:///./data/trip_planner.db')
config.set_main_option('sqlalchemy.url', database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
target_metadata = Base.metadata

# 其他值从配置中获取：
# ... 等等


def run_migrations_offline() -> None:
    """在'离线'模式下运行迁移。

    这将配置上下文，只需一个 URL
    而不是创建引擎，尽管仍然需要引擎来获取
    元数据。

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在'在线'模式下运行迁移。

    在这种情况下，我们需要创建引擎并将其关联到上下文。

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
