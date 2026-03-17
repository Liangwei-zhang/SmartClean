"""Worker Pool — Arq 任務隊列"""
import logging
from arq import create_pool
from arq.connections import RedisSettings
from app.core.config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

_worker_pool = None


def _get_redis_settings() -> RedisSettings:
    """Parse REDIS_URL including password correctly for Arq."""
    url = settings.REDIS_URL
    # redis://:password@host:port/db  OR  redis://host:port/db
    try:
        return RedisSettings.from_dsn(url)
    except Exception:
        # fallback: parse manually
        from urllib.parse import urlparse
        p = urlparse(url)
        return RedisSettings(
            host=p.hostname or "localhost",
            port=p.port or 6379,
            password=p.password or None,
            database=int(p.path.lstrip("/") or 0),
        )


async def get_worker_pool():
    global _worker_pool
    if _worker_pool is None:
        try:
            _worker_pool = await create_pool(_get_redis_settings())
            logger.info("✅ Arq worker pool connected")
        except Exception as exc:
            logger.error("Arq pool connection failed: %s", exc)
            raise
    return _worker_pool


async def close_worker_pool():
    global _worker_pool
    if _worker_pool:
        await _worker_pool.close()
        _worker_pool = None
