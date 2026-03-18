"""异步数据库连接管理模块。

提供 SQLAlchemy 异步引擎和会话管理。
"""

from typing import AsyncGenerator

from sqlalchemy import event
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
    pool_pre_ping=True,  # 检查连接有效性
    pool_recycle=3600,  # 每小时回收连接
)


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """设置 SQLite 优化参数。

    在每个连接创建时执行，启用 WAL 模式和设置超时。
    """
    cursor = dbapi_conn.cursor()
    # 启用 WAL 模式，允许并发读写
    cursor.execute("PRAGMA journal_mode=WAL")
    # 设置 busy_timeout 为 30 秒，等待锁释放
    cursor.execute("PRAGMA busy_timeout=30000")
    # 设置同步模式为 NORMAL，提高性能
    cursor.execute("PRAGMA synchronous=NORMAL")
    # 设置缓存大小为负数表示 KB（-64000 = 64MB）
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.close()


# 为 SQLite 连接设置 PRAGMA
# 注意：需要在引擎创建后、首次使用前注册
@event.listens_for(engine.sync_engine, "connect")
def _on_connect(dbapi_conn, connection_record):
    """连接创建时的回调。"""
    _set_sqlite_pragma(dbapi_conn, connection_record)

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