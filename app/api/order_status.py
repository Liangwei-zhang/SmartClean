"""訂單狀態更新 API — 需要認證"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlmodel import func
from pydantic import BaseModel

from app.core.auth     import get_current_user, require_cleaner, require_host, TokenData
from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Order, OrderStatus, Cleaner

logger = logging.getLogger(__name__)
router = APIRouter()


class StatusUpdate(BaseModel):
    status: str


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id:   int,
    req:        StatusUpdate,
    cleaner_id: int = None,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Depends(get_current_user),   # ← auth
):
    valid = [s.value for s in OrderStatus]
    if req.status not in valid:
        raise HTTPException(status_code=400, detail=f"狀態必須是: {valid}")

    # FIX: validate status value
    try:
        OrderStatus(req.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"無效狀態: {req.status}")

    update_data = {"status": req.status, "updated_at": datetime.utcnow()}
    if req.status == "arrived":
        update_data["arrived_at"]   = datetime.utcnow()
    elif req.status == "completed":
        update_data["completed_at"] = datetime.utcnow()
        # Update cleaner stats atomically
        eff_cleaner = cleaner_id or (token.user_id if token.user_type == "cleaner" else None)
        if eff_cleaner:
            await db.execute(
                update(Cleaner).where(Cleaner.id == eff_cleaner)
                .values(total_jobs=Cleaner.total_jobs + 1, updated_at=datetime.utcnow())
            )

    result = await db.execute(
        update(Order).where(Order.id == order_id).values(**update_data)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="訂單不存在")

    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one()
    # Import shared serializer to avoid code duplication and Enum bugs
    from app.api.orders import serialize_order
    order_data = serialize_order(order)

    from app.core.websocket import manager
    await manager.broadcast("orders", {"type": "status_update", "data": order_data})
    from app.core.cache import delete_pattern
    await delete_pattern("orders:*")
    await delete_pattern("cleaner_orders:*")
    return success_response(data=order_data, message="狀態更新成功")


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    reason:   str = None,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Depends(get_current_user),   # ← auth
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order  = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    if order.status == OrderStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="已完成的訂單無法取消")

    # FIX: only the cleaner on the order or the host can cancel
    if token.user_type == "cleaner" and order.cleaner_id != token.user_id:
        raise HTTPException(status_code=403, detail="無權取消此訂單")

    order.status     = OrderStatus.CANCELLED
    order.updated_at = datetime.utcnow()
    if reason:
        order.text_notes = (order.text_notes or "") + f"\n取消原因: {reason}"
    await db.commit()

    from app.core.websocket import manager
    await manager.broadcast("orders", {"type": "order_cancelled", "order_id": order_id})
    return success_response(message="訂單已取消")


@router.get("/{order_id}/history")
async def get_order_history(order_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order  = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")

    history = [{"status": "open", "time": order.created_at.isoformat() if order.created_at else None, "message": "訂單已發布"}]
    if order.assigned_at:
        history.append({"status": "accepted", "time": order.assigned_at.isoformat(), "message": f"已被 {order.cleaner_name} 接單"})
    if order.arrived_at:
        history.append({"status": "arrived",  "time": order.arrived_at.isoformat(),  "message": "清潔工已到達"})
    if order.completed_at:
        history.append({"status": "completed","time": order.completed_at.isoformat(), "message": "清潔完成"})
    if order.status == OrderStatus.CANCELLED:
        history.append({"status": "cancelled","time": order.updated_at.isoformat() if order.updated_at else None, "message": "訂單已取消"})
    return success_response(data=history)
