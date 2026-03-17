"""异步数据库连接管理模块。

提供 SQLAlchemy 异步引擎和会话管理。
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

# 获取配置
settings = get_settings()

# 创建异步引擎
engine = create_async_engine(
    settings.database_url,
    echo=False,  # 生产环境关闭 SQL 日志
    future=True,
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class DeclarativeBase(DeclarativeBase):
    """SQLAlchemy 声明式基类。

    所有模型类都应继承此类。
    """

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话依赖注入。

    用于 FastAPI 的 Depends 注入。

    Yields:
        AsyncSession: 异步数据库会话
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库。

    创建所有表结构。
    """
    async with engine.begin() as conn:
        await conn.run_sync(DeclarativeBase.metadata.create_all)