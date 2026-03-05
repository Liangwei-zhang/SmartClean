"""
訂單 API - 含樂觀鎖搶單 + WebSocket 廣播
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlmodel import func

from app.core.database import get_db
from app.core.response import success_response, error_response
from app.core.websocket import manager
from app.models.models import Order, OrderStatus, Cleaner, Property, User
from pydantic import BaseModel


def serialize_order(o):
    """將訂單轉為可序列化的字典"""
    data = o.model_dump() if hasattr(o, 'model_dump') else o.__dict__
    for k, v in data.items():
        if hasattr(v, 'isoformat'):
            data[k] = v.isoformat()
    return data


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
    """訂單列表 - 包含房源信息"""
    query = select(Order)
    if status and status != "all":
        query = query.where(Order.status == status)
    query = query.order_by(Order.created_at.desc())
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    # 獲取每個訂單的房源信息
    order_list = []
    for o in orders:
        order_data = serialize_order(o)
        
        # 獲取房源信息
        prop_result = await db.execute(
            select(Property).where(Property.id == o.property_id)
        )
        prop = prop_result.scalar_one_or_none()
        if prop:
            order_data['property_name'] = prop.name
            order_data['property_address'] = prop.address
        order_data['host_phone'] = None
        
        # 獲取房東電話
        if o.host_id:
            user_result = await db.execute(
                select(User).where(User.id == o.host_id)
            )
            user = user_result.scalar_one_or_none()
            if user and user.phone:
                order_data['host_phone'] = user.phone if user else None
        
        order_list.append(order_data)
    
    return success_response(data=order_list)


@router.post("")
async def create_order(req: CreateOrderRequest, db: AsyncSession = Depends(get_db)):
    """創建訂單"""
    # 轉換時間格式
    checkout_time = None
    if req.checkout_time:
        try:
            checkout_time = datetime.fromisoformat(req.checkout_time.replace('Z', '+00:00'))
        except:
            checkout_time = req.checkout_time
    
    # 檢查重複訂單 (相同房源 + 相同時間)
    if req.property_id and checkout_time:
        existing = await db.execute(
            select(Order).where(
                Order.property_id == req.property_id,
                Order.checkout_time == checkout_time,
                Order.status == OrderStatus.OPEN
            )
        )
        if existing.first():
            raise HTTPException(
                status_code=400, 
                detail="該房源在此時間已有未完成訂單"
            )
    
    order = Order(
        property_id=req.property_id,
        host_id=req.host_id,
        host_name=req.host_name,
        host_phone=req.host_phone,
        price=req.price,
        checkout_time=checkout_time,
        text_notes=req.text_notes,
        status=OrderStatus.OPEN,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    # 🔥 廣播新訂單 (轉為字典型)
    order_data = serialize_order(order)
    
    await manager.broadcast("orders", {
        "type": "new_order",
        "data": order_data
    })
    
    return success_response(data=serialize_order(order), message="訂單創建成功")


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
    order_data = serialize_order(updated_order)
    
    await manager.broadcast("orders", {
        "type": "order_accepted",
        "data": order_data
    })
    
    return success_response(message="搶單成功")


@router.patch("/{order_id}")
@router.put("/{order_id}")
async def update_order(
    order_id: int,
    req: dict,
    db: AsyncSession = Depends(get_db)
):
    """更新訂單"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    # 更新字段
    if "status" in req:
        order.status = req["status"]
        if req["status"] == "arrived":
            order.arrived_at = func.now()
        elif req["status"] == "completed":
            order.completed_at = func.now()
    
    if "completion_photos" in req:
        order.completion_photos = req["completion_photos"]
    
    if "cleaner_id" in req:
        order.cleaner_id = req["cleaner_id"]
    
    if "cleaner_name" in req:
        order.cleaner_name = req["cleaner_name"]
    
    if "price" in req:
        order.price = req["price"]
    
    if "text_notes" in req:
        order.text_notes = req["text_notes"]
    
    if "checkout_time" in req:
        order.checkout_time = req["checkout_time"]
    
    await db.commit()
    await db.refresh(order)
    
    return success_response(data=serialize_order(order))


@router.get("/{order_id}")
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    """訂單詳情"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    return success_response(data=serialize_order(order))


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


@router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db)
):
    """刪除訂單"""
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    await db.delete(order)
    await db.commit()
    
    return success_response(message="刪除成功")
