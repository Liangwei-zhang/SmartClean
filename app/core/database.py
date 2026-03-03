from sqlmodel import SQLModel, create_engine, Session, Field
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import get_settings

settings = get_settings()

# 異步步驅動引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

# 同步引擎 (遷移用)
engine_sync = create_engine(
    settings.DATABASE_URL_SYNC,
    echo=settings.DEBUG,
)

# 會話工廠
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """依賴注入 - 數據庫會話"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化數據庫"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
