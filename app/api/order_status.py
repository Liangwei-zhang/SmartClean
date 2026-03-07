"""
訂單狀態更新 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlmodel import func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Order, OrderStatus, Cleaner

router = APIRouter()


class StatusUpdate(BaseModel):
    status: str  # accepted/arrived/completed/cancelled


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: int,
    req: StatusUpdate,
    cleaner_id: int = None,
    db: AsyncSession = Depends(get_db)
):
    """更新訂單狀態"""
    # 驗證狀態
    valid_statuses = [s.value for s in OrderStatus]
    if req.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"狀態必須是: {valid_statuses}")
    
    # 構建更新數據
    update_data = {"status": req.status}
    
    if req.status == "arrived":
        update_data["arrived_at"] = func.now()
    elif req.status == "completed":
        update_data["completed_at"] = func.now()
        # 完成訂單，增加清潔工統計
        if cleaner_id:
            result = await db.execute(
                select(Cleaner).where(Cleaner.id == cleaner_id)
            )
            cleaner = result.scalar_one_or_none()
            if cleaner:
                cleaner.total_jobs += 1
    
    # 樂觀鎖更新
    result = await db.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(**update_data)
    )
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    # 獲取更新後的訂單
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one()
    
    # 安全序列化
    try:
        order_data = order.model_dump() if hasattr(order, 'model_dump') else dict(order.__dict__)
        for k, v in order_data.items():
            if hasattr(v, 'isoformat'):
                order_data[k] = v.isoformat()
    except Exception as e:
        order_data = {"id": order.id, "status": str(order.status)}
    
    # 廣播狀態更新
    from app.core.websocket import manager
    await manager.broadcast("orders", {
        "type": "status_update",
        "data": order_data
    })
    
    return success_response(data=order_data, message="狀態更新成功")


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    reason: str = None,
    db: AsyncSession = Depends(get_db)
):
    """取消訂單"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    if order.status == OrderStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="已完成的訂單無法取消")
    
    # 只能由房東或清潔工取消
    order.status = OrderStatus.CANCELLED
    if reason:
        order.text_notes = (order.text_notes or "") + f"\n取消原因: {reason}"
    
    await db.commit()
    
    # 廣播取消
    from app.core.websocket import manager
    await manager.broadcast("orders", {
        "type": "order_cancelled",
        "order_id": order_id
    })
    
    return success_response(message="訂單已取消")


@router.get("/{order_id}/history")
async def get_order_history(order_id: int, db: AsyncSession = Depends(get_db)):
    """訂單歷史 (狀態變更記錄)"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    history = [
        {"status": "open", "time": order.created_at, "message": "訂單已發布"},
    ]
    
    if order.assigned_at:
        history.append({
            "status": "accepted", 
            "time": order.assigned_at, 
            "message": f"已被 {order.cleaner_name} 接單"
        })
    
    if order.arrived_at:
        history.append({
            "status": "arrived",
            "time": order.arrived_at,
            "message": "清潔工已到達"
        })
    
    if order.completed_at:
        history.append({
            "status": "completed",
            "time": order.completed_at,
            "message": "清潔完成"
        })
    
    if order.status == OrderStatus.CANCELLED:
        history.append({
            "status": "cancelled",
            "time": order.updated_at,
            "message": "訂單已取消"
        })
    
    return success_response(data=history)
