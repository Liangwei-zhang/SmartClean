"""
Arq 任務隊列 - 替換 Celery
比 Celery 快數倍，完美融合 FastAPI
"""
import asyncio
import logging
from datetime import datetime
from arq import create_pool, Actor
from arq.connections import RedisSettings

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


# --- 任務定義 ---
async def send_notification(ctx, user_id: int, title: str, body: str):
    """發送通知任務"""
    from app.services.notifications import send_push_notification
    await send_push_notification(user_id, title, body)


async def notify_new_order(ctx, order_id: int, cleaner_ids: list):
    """新訂單通知"""
    from app.services.notifications import notify_new_order as send_notify
    await send_notify(ctx, order_id, cleaner_ids)


async def notify_order_accepted(ctx, order_id: int, host_id: int, cleaner_name: str):
    """訂單被接通知"""
    from app.services.notifications import notify_order_accepted as send_notify
    await send_notify(ctx, order_id, host_id, cleaner_name)


async def notify_order_completed(ctx, order_id: int, host_id: int, cleaner_name: str):
    """訂單完成通知"""
    from app.services.notifications import notify_order_completed as send_notify
    await send_notify(ctx, order_id, host_id, cleaner_name)


async def cleanup_old_orders(ctx, days: int = 30):
    """清理舊訂單"""
    logger.info(f"🧹 清理 {days} 天前的訂單")
    # 實現清理邏輯


async def sync_cleaner_location(ctx, cleaner_id: int, lat: float, lng: float):
    """同步清潔工位置"""
    logger.info(f"📍 清潔工 {cleaner_id} 位置: {lat}, {lng}")
    # 實現位置同步邏輯


class WorkerSettings:
    """Arq Worker 設置"""
    functions = [
        send_notification,
        notify_new_order,
        notify_order_accepted,
        notify_order_completed,
        cleanup_old_orders,
        sync_cleaner_location,
    ]
    redis_settings = RedisSettings.from_url(settings.REDIS_URL)
    health_check_msg = "health_check"
    health_check_latency = 5


# --- 客戶端 ---
async def enqueue_task(task_name: str, *args, **kwargs):
    """入隊任務"""
    async with create_pool(RedisSettings.from_url(settings.REDIS_URL)) as pool:
        await pool.enqueue(task_name, *args, **kwargs)


# 快捷方法
async def notify(user_id: int, title: str, body: str):
    await enqueue_task("send_notification", user_id, title, body)


async def cleanup_orders(days: int = 30):
    await enqueue_task("cleanup_old_orders", days)
