"""
訂單 API - 含樂觀鎖搶單 + WebSocket 廣播
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlmodel import func

from app.core.database import get_db
from app.core.response import success_response, error_response
from app.core.websocket import manager
from app.models.models import Order, OrderStatus, Cleaner
from pydantic import BaseModel

router = APIRouter()


# --- Schema ---
class CreateOrderRequest(BaseModel):
    property_id: int
    price: float
    checkout_time: str
    host_id: int | None = None
    host_name: str | None = None
    host_phone: str | None = None
    text_notes: str | None = None


class AcceptOrderRequest(BaseModel):
    cleaner_id: int
    cleaner_name: str | None = None


# --- REST API ---

@router.get("")
async def list_orders(
    status: str = "open",
    db: AsyncSession = Depends(get_db)
):
    """訂單列表"""
    query = select(Order)
    if status:
        query = query.where(Order.status == status)
    query = query.order_by(Order.created_at.desc())
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    return success_response(data=[o.model_dump() for o in orders])


@router.post("")
async def create_order(req: CreateOrderRequest, db: AsyncSession = Depends(get_db)):
    """創建訂單"""
    order = Order(
        property_id=req.property_id,
        host_id=req.host_id,
        host_name=req.host_name,
        host_phone=req.host_phone,
        price=req.price,
        checkout_time=req.checkout_time,
        text_notes=req.text_notes,
        status=OrderStatus.OPEN,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    # 🔥 廣播新訂單
    await manager.broadcast("orders", {
        "type": "new_order",
        "data": order.model_dump()
    })
    
    return success_response(data=order.model_dump(), message="訂單創建成功")


@router.post("/{order_id}/accept")
async def accept_order(
    order_id: int,
    req: AcceptOrderRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    搶單 - 樂觀鎖實現
    防止並發 Race Condition
    """
    # 1. 查詢訂單當前版本
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    if order.status != OrderStatus.OPEN:
        raise HTTPException(status_code=400, detail="訂單已被搶走")
    
    # 2. 樂觀鎖更新
    result = await db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.version == order.version,
            Order.status == OrderStatus.OPEN
        )
        .values(
            status=OrderStatus.ACCEPTED,
            cleaner_id=req.cleaner_id,
            cleaner_name=req.cleaner_name,
            version=order.version + 1,
            assigned_at=func.now()
        )
    )
    
    # 3. 檢查是否更新成功
    if result.rowcount == 0:
        raise HTTPException(
            status_code=409, 
            detail="搶單失敗，訂單已被其他人搶走"
        )
    
    await db.commit()
    
    # 重新獲取更新後的訂單
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    updated_order = result.scalar_one()
    
    # 🔥 廣播搶單結果
    await manager.broadcast("orders", {
        "type": "order_accepted",
        "data": updated_order.model_dump()
    })
    
    return success_response(message="搶單成功")


@router.get("/{order_id}")
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    """訂單詳情"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    return success_response(data=order.model_dump())


# --- WebSocket ---

@router.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    """訂單即時 WebSocket"""
    await manager.connect(websocket, "orders")
    try:
        while True:
            # 保持連接，等待廣播
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "orders")
