"""
Arq Worker 配置
訂單超時處理任務隊列
"""
from datetime import timedelta
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.tasks.order_tasks import OrderTasks

settings = get_settings()


class WorkerSettings:
    """Arq Worker 配置"""
    
    redis_settings = RedisSettings.from_url(settings.REDIS_URL)
    
    # 任務函數
    functions = [
        OrderTasks.expand_order_search,
        OrderTasks.cancel_order,
        OrderTasks.notify_host_order_timeout,
    ]
    
    # 任務設置
    job_timeout = 300  # 單個任務超時 5 分鐘
    max_tries = 3  # 最大重試次數
    retry_delay = 10  # 重試延遲 (秒)
    
    # 健康檢查
    health_check_interval = 60
    
    # 周期任務 (cron-like)
    # on_startup / on_shutdown 可以用於初始化/清理


async def enqueue_order_tasks(order_id: int, property_lat: float = None, property_lon: float = None):
    """
    為訂單排隊異步任務
    
    調用示例:
    await enqueue_order_tasks(123, 51.0447, -114.0719)
    """
    from app.core.worker import get_worker_pool
    
    pool = await get_worker_pool()
    
    # 30秒後擴展搜索範圍 (5km -> 10km)
    await pool.enqueue_in(
        timedelta(seconds=30),
        "order_tasks.expand_order_search",
        order_id,
        5, 10
    )
    
    # 60秒後擴展 (10km -> 20km)
    await pool.enqueue_in(
        timedelta(seconds=60),
        "order_tasks.expand_order_search",
        order_id,
        10, 20
    )
    
    # 120秒後仍未接單則取消
    await pool.enqueue_in(
        timedelta(seconds=120),
        "order_tasks.cancel_order",
        order_id,
        "timeout"
    )
    
    print(f"📅 為訂單 {order_id} 排隊了異步任務")
