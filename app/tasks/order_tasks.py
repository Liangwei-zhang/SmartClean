"""
訂單異步任務 — Arq Worker
FIX: get_db_session() now properly imported; asyncio.sleep inside expand removed
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def expand_order_search(ctx, order_id: int, current_radius_km: float, max_radius_km: float = 50):
    """擴大派單範圍 — Arq task (no asyncio.sleep inside)"""
    from app.core.database import get_db_session   # FIX: properly defined now
    from app.models.models import Order, OrderStatus, Property
    from sqlalchemy import select

    async with get_db_session() as db:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order  = result.scalar_one_or_none()
        if not order or order.status != OrderStatus.OPEN:
            return

        prop_r = await db.execute(select(Property).where(Property.id == order.property_id))
        prop   = prop_r.scalar_one_or_none()
        if not prop or not prop.latitude:
            return

    new_radius = min(current_radius_km + 10, max_radius_km)
    try:
        from app.core.geo import geo_service
        nearby = await geo_service.get_nearby_cleaners(
            lat=prop.latitude, lon=prop.longitude, radius_km=new_radius, limit=50)
        if nearby:
            from app.core.websocket import manager
            await manager.dispatch_to_cleaners(
                cleaner_ids=[c["id"] for c in nearby],
                order_data={"id": order.id, "price": order.price, "expanded": True, "new_radius": new_radius},
                require_ack=False,
            )
    except Exception as exc:
        logger.error("expand_order_search error: %s", exc)

    logger.info("📍 Order %d search expanded to %.0fkm", order_id, new_radius)


async def cancel_order(ctx, order_id: int, reason: str = "timeout"):
    """取消超時訂單 — Arq task"""
    from app.core.database import get_db_session
    from app.models.models import Order, OrderStatus
    from sqlalchemy import select

    async with get_db_session() as db:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order  = result.scalar_one_or_none()
        if not order or order.status != OrderStatus.OPEN:
            return
        order.status     = OrderStatus.CANCELLED
        order.text_notes = f"{order.text_notes or ''}\n[系統] 自動取消: {reason}"
        order.updated_at = datetime.utcnow()
        await db.commit()

    try:
        from app.core.websocket import manager
        await manager.broadcast("orders", {"type": "order_cancelled",
                                            "data": {"order_id": order_id, "reason": reason}})
    except Exception as exc:
        logger.warning("WS broadcast on cancel failed: %s", exc)

    logger.info("❌ Order %d auto-cancelled: %s", order_id, reason)


async def notify_host_order_timeout(ctx, order_id: int):
    """通知房東超時 — Arq task (placeholder for SMS/push)"""
    logger.info("📱 Host notified for order %d timeout", order_id)
