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
from app.core.cache import get_from_cache, set_cache, cache_key, delete_pattern
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
    limit: int = None,
    offset: int = 0,
    cleaner_lat: float = None,
    cleaner_lon: float = None,
    db: AsyncSession = Depends(get_db)
):
    """訂單列表 - 包含房源信息 (含緩存 + 分頁 + 距離)"""
    # 如果不傳 limit，返回所有數據（不分頁）
    if limit is None:
        limit = 10000  # 較大的數字
    
    # 緩存 key 包含分頁參數和清潔員位置
    cache_key_str = cache_key("orders", status=status, limit=limit, offset=offset, cleaner_lat=cleaner_lat, cleaner_lon=cleaner_lon)
    cached = await get_from_cache(cache_key_str)
    if cached is not None:
        return cached
    
    # 使用 JOIN 一次性獲取訂單和房源信息
    query = (
        select(Order, Property)
        .outerjoin(Property, Order.property_id == Property.id)
        .outerjoin(User, Order.host_id == User.id)
    )
    
    if status and status != "all":
        query = query.where(Order.status == status)
    # 獲取總數
    count_query = select(func.count(Order.id))
    if status and status != "all":
        count_query = count_query.where(Order.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分頁
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    rows = result.all()
    
    # 處理結果
    order_list = []
    for row in rows:
        o = row[0]
        prop = row[1] if len(row) > 1 else None
        
        order_data = serialize_order(o)
        
        # 房源信息
        if prop:
            order_data['property_name'] = prop.name
            order_data['property_address'] = prop.address
            if prop.host_phone:
                order_data['host_phone'] = prop.host_phone
            # 添加坐標
            if prop.latitude:
                order_data['property_lat'] = prop.latitude
                order_data['property_lng'] = prop.longitude
                
                # 計算距離 (如果提供了清潔員位置)
                if cleaner_lat and cleaner_lon:
                    from app.core.geo import geo_service
                    distance = await geo_service.calculate_distance(
                        cleaner_lat, cleaner_lon,
                        prop.latitude, prop.longitude
                    )
                    if distance is not None:
                        order_data['distance_km'] = round(distance, 1)
        
        order_list.append(order_data)
    
    # 設置緩存 (L1: 5秒, L2: 30秒) - 存儲完整響應
    cache_response = {
        "success": True,
        "data": order_list,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(order_list) < total
        }
    }
    await set_cache(cache_key_str, cache_response, ttl_l1=5, ttl_l2=30)
    
    # 返回帶分頁信息
    return cache_response


@router.get("/cleaner/{cleaner_id}")
async def get_cleaner_orders(
    cleaner_id: int,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """清潔員訂單列表 (含緩存)"""
    # 嘗試從緩存獲取
    cache_key_str = cache_key("cleaner_orders", cleaner_id=cleaner_id)
    cached = await get_from_cache(cache_key_str)
    if cached is not None:
        return success_response(data=cached)
    
    # 查詢清潔員的訂單
    query = (
        select(Order, Property)
        .outerjoin(Property, Order.property_id == Property.id)
        .where(Order.cleaner_id == cleaner_id)
        .where(Order.status != OrderStatus.OPEN)
        .order_by(Order.created_at.desc())
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    order_list = []
    for row in rows:
        o = row[0]
        prop = row[1] if len(row) > 1 else None
        
        order_data = serialize_order(o)
        
        if prop:
            order_data['property_name'] = prop.name
            order_data['property_address'] = prop.address
        
        order_list.append(order_data)
    
    # 設置緩存 (L1: 2秒, L2: 5秒) - 短TTL支持即時更新
    await set_cache(cache_key_str, order_list, ttl_l1=2, ttl_l2=5)
    
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
    
    # 清除訂單列表緩存 (立即清除，不等待TTL)
    await delete_pattern("orders:*")
    await delete_pattern("cleaner_orders:*")
    
    # === 3. 同步到 Redis (支持高速搶單) ===
    try:
        from app.core.accept_script import order_script
        await order_script.sync_order_to_redis(order_data)
    except Exception as e:
        print(f"Redis 同步失敗: {e}")
    
    # === 4. 調度異步任務 (超時處理) ===
    try:
        from app.core.worker import get_worker_pool
        pool = await get_worker_pool()
        
        if property and property.latitude and property.longitude:
            # 30秒後擴展搜索範圍
            await pool.enqueue_in(30, "order_tasks.expand_order_search", order.id, 5, 10)
            # 60秒後再擴展
            await pool.enqueue_in(60, "order_tasks.expand_order_search", order.id, 10, 20)
            # 120秒後仍未接單則取消
            await pool.enqueue_in(120, "order_tasks.cancel_order", order.id, "timeout")
    except Exception as e:
        print(f"異步任務調度失敗: {e}")
    
    # 2. 定向派單給附近在線清潔員
    try:
        # 獲取房源位置
        prop_result = await db.execute(
            select(Property).where(Property.id == req.property_id)
        )
        property = prop_result.scalar_one_or_none()
        
        if property and property.latitude and property.longitude:
            # 查找附近 10km 內的在線清潔員
            from app.core.geo import geo_service
            nearby = await geo_service.get_nearby_cleaners(
                lat=property.latitude,
                lon=property.longitude,
                radius_km=10,
                limit=20
            )
            
            if nearby:
                cleaner_ids = [c["id"] for c in nearby]
                # 定向派單
                await manager.dispatch_to_cleaners(
                    cleaner_ids=cleaner_ids,
                    order_data=order_data,
                    require_ack=True
                )
    except Exception as e:
        print(f"定向派單失敗: {e}")
    
    return success_response(data=serialize_order(order), message="訂單創建成功")


@router.post("/{order_id}/accept")
async def accept_order(
    order_id: int,
    req: AcceptOrderRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    搶單 - 悲觀鎖實現
    使用 SELECT FOR UPDATE SKIP LOCKED 防止並發 Race Condition
    """
    # 1. 悲觀鎖查詢 + 鎖定訂單
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update(skip_locked=True)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    
    if order.status != OrderStatus.OPEN:
        raise HTTPException(status_code=400, detail="訂單已被搶走")
    
    # 2. 更新訂單狀態
    order.status = OrderStatus.ACCEPTED
    order.cleaner_id = req.cleaner_id
    order.cleaner_name = req.cleaner_name
    order.assigned_at = func.now()
    order.version += 1
    
    await db.commit()
    await db.refresh(order)
    
    # 重新獲取更新後的訂單
    result = await db.execute(
        select(Order).where(Order.id == order_id)
    )
    updated_order = result.scalar_one()
    
    # 🔥 廣播搶單結果
    order_data = serialize_order(updated_order)
    
    await manager.broadcast("orders", {
        "type": "order_accepted",
        "data": {"order_id": order_id, "cleaner_id": req.cleaner_id, "order": order_data}
    })
    
    # 🔥 通知其他清潔員訂單已被搶走
    await manager.notify_order_taken(order_id, req.cleaner_id)
    
    # 清除緩存
    await delete_pattern("orders:*")
    await delete_pattern("cleaner_orders:*")
    
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
    
    if "accepted_by_host" in req:
        order.accepted_by_host = bool(req["accepted_by_host"])
    
    await db.commit()
    await db.refresh(order)
    
    # 清除訂單列表緩存
    await delete_pattern("orders:*")
    await delete_pattern("cleaner_orders:*")
    
    # 廣播訂單更新
    await manager.broadcast("orders", {
        "type": "order_updated",
        "data": serialize_order(order)
    })
    
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
@router.websocket("/ws/orders/{cleaner_id}")
async def websocket_orders(websocket: WebSocket, cleaner_id: int = None):
    """訂單即時 WebSocket
    
    支持傳入 cleaner_id 用於定向派單:
    - ws://host/api/orders/ws/orders/123 (cleaner_id=123)
    - ws://host/api/orders/ws/orders (廣播模式)
    """
    await manager.connect(websocket, "orders", cleaner_id=cleaner_id)
    try:
        while True:
            data = await websocket.receive_text()
            
            # 解析消息
            try:
                import json
                msg = json.loads(data) if data != "ping" else {"type": "ping"}
            except:
                msg = {"type": "unknown"}
            
            # 心跳/ping 回應
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            
            # ACK 確認
            elif msg.get("type") == "ack":
                message_id = msg.get("message_id")
                if message_id:
                    await manager.handle_ack(message_id)
                    
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
    
    # 清除訂單列表緩存
    await delete_pattern("orders:*")
    
    return success_response(message="刪除成功")
