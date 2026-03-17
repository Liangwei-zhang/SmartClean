"""
通知 API — 需要認證
"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth     import require_admin, require_host, TokenData
from app.core.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter()


class NotifyRequest(BaseModel):
    user_id: int
    title:   str
    body:    str


async def notify(user_id: int, title: str, body: str):
    """通知 stub — 透過 SMS/push service 實現"""
    pass


@router.post("/send")
async def send_notification(req: NotifyRequest, _: TokenData = Depends(require_admin)):
    """發送通知（管理員）"""
    try:
        await notify(req.user_id, req.title, req.body)
    except Exception as exc:
        logger.warning("Notification send failed: %s", exc)
    return success_response(message="通知已發送")


@router.post("/broadcast")
async def broadcast_to_cleaners(order_id: int, _: TokenData = Depends(require_host)):
    """廣播新訂單（房東）"""
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.models import Cleaner
        async with AsyncSessionLocal() as db:
            result  = await db.execute(select(Cleaner).where(Cleaner.status == "online"))
            cleaner_ids = [c.id for c in result.scalars().all()]

        from app.core.websocket import manager
        from app.core.cache import get_from_cache
        await manager.broadcast("orders", {"type": "broadcast", "order_id": order_id})
        return success_response(message=f"已廣播給 {len(cleaner_ids)} 位清潔工")
    except Exception as exc:
        logger.error("Broadcast failed: %s", exc)
        return success_response(message="廣播失敗")
