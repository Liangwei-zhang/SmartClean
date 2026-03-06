"""
Worker Pool 管理
"""
import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

settings = get_settings()

_worker_pool = None


async def get_worker_pool():
    """獲取 Worker 連接池"""
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = await create_pool(
            RedisSettings.from_url(settings.REDIS_URL)
        )
    return _worker_pool


async def close_worker_pool():
    """關閉 Worker 連接池"""
    global _worker_pool
    if _worker_pool:
        await _worker_pool.close()
        _worker_pool = None
