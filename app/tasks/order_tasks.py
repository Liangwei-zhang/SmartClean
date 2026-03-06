"""
異步任務鏈 - 訂單超時自動處理
使用 Arq 實現延時任務
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import json

from app.core.database import get_db_session
from app.core.cache import get_redis, delete_pattern
from app.core.websocket import manager
from app.core.geo import geo_service
from app.models.models import Order, OrderStatus


class OrderTasks:
    """訂單相關的異步任務"""
    
    @staticmethod
    async def cleanup_stale_orders():
        """
        清理超時未接單的訂單
        調度: 每分鐘執行一次
        """
        # 這是一個示例，實際應使用 Arq 的 cron 語法
        pass
    
    @staticmethod
    async def expand_order_search(
        order_id: int,
        current_radius_km: float,
        max_radius_km: float = 50,
        step_km: float = 10
    ):
        """
        擴大訂單搜索範圍
        
        場景: 訂單發布 30 秒後未被搶，自動擴大範圍推送
        """
        if current_radius_km >= max_radius_km:
            # 達到最大範圍，放棄訂單
            await OrderTasks.cancel_order(order_id, "timeout")
            return
        
        # 查詢訂單
        async for db in get_db_session():
            from sqlalchemy import select
            result = await db.execute(
                select(Order).where(Order.id == order_id)
            )
            order = result.scalar_one_or_none()
            
            if not order or order.status != OrderStatus.OPEN:
                return  # 訂單已被接或已取消
            
            # 查詢房源位置
            from sqlalchemy import select as s
            from app.models.models import Property
            prop_result = await db.execute(
                s(Property).where(Property.id == order.property_id)
            )
            prop = prop_result.scalar_one_or_none()
            
            if not prop or not prop.latitude:
                return
            
            # 擴大範圍搜索
            new_radius = min(current_radius_km + step_km, max_radius_km)
            
            nearby = await geo_service.get_nearby_cleaners(
                lat=prop.latitude,
                lon=prop.longitude,
                radius_km=new_radius,
                limit=50
            )
            
            if nearby:
                # 定向派單
                cleaner_ids = [c["id"] for c in nearby]
                await manager.dispatch_to_cleaners(
                    cleaner_ids=cleaner_ids,
                    order_data={
                        "id": order.id,
                        "price": order.price,
                        "property_name": prop.name,
                        "property_address": prop.address,
                        "expanded": True,  # 標記為擴展推送
                        "original_radius": current_radius_km,
                        "new_radius": new_radius
                    },
                    require_ack=False
                )
            
            # 記錄日誌
            print(f"📍 訂單 {order_id} 擴大範圍: {current_radius_km}km -> {new_radius}km")
            
            # 安排下次擴展
            await asyncio.sleep(30)  # 30秒後再次檢查
    
    @staticmethod
    async def cancel_order(order_id: int, reason: str = "timeout"):
        """
        取消超時訂單
        """
        async for db in get_db_session():
            from sqlalchemy import select
            result = await db.execute(
                select(Order).where(Order.id == order_id)
            )
            order = result.scalar_one_or_none()
            
            if not order or order.status != OrderStatus.OPEN:
                return
            
            order.status = OrderStatus.CANCELLED
            
            # 記錄取消原因
            order.text_notes = f"{order.text_notes or ''}\n[系統] 自動取消: {reason}"
            
            await db.commit()
            
            # 廣播訂單取消
            await manager.broadcast("orders", {
                "type": "order_cancelled",
                "data": {
                    "order_id": order_id,
                    "reason": reason
                }
            })
            
            print(f"❌ 訂單 {order_id} 已自動取消: {reason}")
    
    @staticmethod
    async def notify_host_order_timeout(order_id: int):
        """
        通知房東訂單長時間未被接單
        """
        # 實現通知邏輯 (短信/推送)
        print(f"📱 通知房東訂單 {order_id} 超時未接單")
    
    @staticmethod
    async def schedule_order_timeout_check(order_id: int, timeout_minutes: int = 30):
        """
        調度訂單超時檢查
        
        應在創建訂單時調用:
        await OrderTasks.schedule_order_timeout_check(order_id, 30)
        """
        # 這需要 Arq 的延時任務支持
        # 實際實現取決於 Arq 配置
        pass


class OrderScheduler:
    """
    訂單調度器
    管理訂單的生命週期
    """
    
    @staticmethod
    async def create_order_with_tracking(order_id: int, property_lat: float, property_lon: float):
        """
        創建訂單並設置追蹤
        
        流程:
        1. 立即推送附近 5km 清潔員
        2. 30秒後擴展到 10km
        3. 60秒後擴展到 20km
        4. 90秒後擴展到 50km
        5. 120秒後仍未接單則取消
        """
        # 記錄到 Redis (用於追蹤)
        r = await get_redis()
        if r:
            await r.hset(
                f"order:tracking:{order_id}",
                mapping={
                    "status": "open",
                    "property_lat": str(property_lat),
                    "property_lon": str(property_lon),
                    "created_at": str(datetime.now().timestamp())
                }
            )
            await r.expire(f"order:tracking:{order_id}", 300)  # 5分鐘過期
        
        # 啟動擴展任務 (實際應使用 Arq)
        # asyncio.create_task(OrderTasks.expand_order_search(order_id, 5, 10))
        # asyncio.create_task(asyncio.sleep(60, OrderTasks.expand_order_search(order_id, 10, 20)))
        # ...
    
    @staticmethod
    async def on_order_accepted(order_id: int):
        """訂單被接中時調用，取消所有相關的超時任務"""
        r = await get_redis()
        if r:
            await r.hset(
                f"order:tracking:{order_id}",
                "status",
                "accepted"
            )
    
    @staticmethod
    async def on_order_cancelled(order_id: int):
        """訂單取消時調用"""
        r = await get_redis()
        if r:
            await r.hset(
                f"order:tracking:{order_id}",
                "status",
                "cancelled"
            )
            await r.delete(f"order:tracking:{order_id}")
