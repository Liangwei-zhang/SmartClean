"""
數據庫引擎與會話管理
FIX: 新增 get_db_session() 異步生成器供後台任務使用
"""
import logging
from contextlib import asynccontextmanager

from sqlmodel import SQLModel, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

# ── 異步引擎（應用用） ────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=30,           # 100萬日活：增加連接池
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=1800,      # 每30分鐘回收空閒連接
)

# ── 同步引擎（遷移用） ────────────────────────────────────────────────────────
engine_sync = create_engine(settings.DATABASE_URL_SYNC, echo=settings.DEBUG)

# ── 會話工廠 ─────────────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI Depends 依賴注入"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_session():
    """
    FIX: 後台任務（Arq worker）使用的異步上下文管理器
    用法: async with get_db_session() as db: ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """初始化數據庫表結構"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("✅ Database tables initialized")
