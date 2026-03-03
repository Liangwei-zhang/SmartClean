"""
通知 API - 觸發通知
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.response import success_response

router = APIRouter()


class NotifyRequest(BaseModel):
    user_id: int
    title: str
    body: str


@router.post("/send")
async def send_notification(req: NotifyRequest):
    """發送通知"""
    from app.tasks.worker import notify
    await notify(req.user_id, req.title, req.body)
    return success_response(message="通知已發送")


@router.post("/broadcast")
async def broadcast_to_cleaners(order_id: int):
    """廣播新訂單給清潔工"""
    from app.tasks.worker import enqueue_task
    # 獲取所有在線清潔工
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models.models import Cleaner
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Cleaner).where(Cleaner.status == "online")
        )
        cleaners = result.scalars().all()
        cleaner_ids = [c.id for c in cleaners]
    
    await enqueue_task("notify_new_order", order_id, cleaner_ids)
    return success_response(message=f"已廣播給 {len(cleaner_ids)} 位清潔工")
