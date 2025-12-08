"""
数据库连接与 Session 管理。

这里使用 SQLAlchemy 的异步引擎 + aiomysql，以便后续更容易扩展为高并发场景。
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings


# SQLAlchemy 基类，用于定义 ORM 模型
Base = declarative_base()


def _build_mysql_url() -> str:
    """根据配置拼接 MySQL 的 async 连接 URL。"""
    return (
        f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_db}"
        "?charset=utf8mb4"
    )


DATABASE_URL = _build_mysql_url()

# 创建异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # 调试阶段可以设置为 True 查看 SQL
    pool_pre_ping=True,
)

# 创建异步 Session 工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db():
    """
    FastAPI 依赖项：获取一个数据库 Session。

    使用示例：
        async def api_handler(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    初始化数据库结构。

    开发阶段可以通过在程序启动时调用该函数来自动建表；
    正式环境建议使用 Alembic 做迁移管理。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

