"""
Arq 任務隊列 - 替換 Celery
比 Celery 快數倍，完美融合 FastAPI
"""
import asyncio
from datetime import datetime
from arq import create_pool, Actor
from arq.connections import RedisSettings

from app.core.config import get_settings

settings = get_settings()


# --- 任務定義 ---
async def send_notification(ctx, user_id: int, title: str, body: str):
    """發送通知任務"""
    # 實現通知邏輯 (推送/郵件等)
    print(f"📱 通知用戶 {user_id}: {title} - {body}")


async def cleanup_old_orders(ctx, days: int = 30):
    """清理舊訂單"""
    print(f"🧹 清理 {days} 天前的訂單")
    # 實現清理邏輯


async def sync_cleaner_location(ctx, cleaner_id: int, lat: float, lng: float):
    """同步清潔工位置"""
    print(f"📍 清潔工 {cleaner_id} 位置: {lat}, {lng}")
    # 實現位置同步邏輯


class WorkerSettings:
    """Arq Worker 設置"""
    functions = [
        send_notification,
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
