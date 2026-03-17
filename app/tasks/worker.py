"""Arq Worker 配置"""
from arq.connections import RedisSettings
from app.core.config import get_settings
from app.tasks.order_tasks import expand_order_search, cancel_order, notify_host_order_timeout

settings = get_settings()


class WorkerSettings:
    redis_settings = RedisSettings.from_url(settings.REDIS_URL)
    functions      = [expand_order_search, cancel_order, notify_host_order_timeout]
    job_timeout    = 300
    max_tries      = 3
    retry_delay    = 10
    health_check_interval = 60


async def enqueue_order_tasks(order_id: int, property_lat: float = None, property_lon: float = None):
    from datetime import timedelta
    from app.core.worker import get_worker_pool
    pool = await get_worker_pool()
    await pool.enqueue_in(timedelta(seconds=30),  "expand_order_search", order_id, 5,  10)
    await pool.enqueue_in(timedelta(seconds=60),  "expand_order_search", order_id, 10, 20)
    await pool.enqueue_in(timedelta(seconds=120), "cancel_order",        order_id, "timeout")
    import logging; logging.getLogger(__name__).info("Enqueued tasks for order %d", order_id)
