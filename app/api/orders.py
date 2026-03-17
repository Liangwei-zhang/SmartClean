"""
訂單 API — 悲觀鎖搶單 + WebSocket 廣播
安全：寫操作需要 JWT；讀操作開放（清潔員可看到訂單列表）
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlmodel import func

from app.core.auth     import require_cleaner, require_host, get_current_user, optional_user, TokenData
from app.core.database import get_db
from app.core.response import success_response
from app.core.websocket import manager
from app.core.cache    import get_from_cache, set_cache, cache_key, delete_pattern
from app.models.models import Order, OrderStatus, Property
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

# MAX safe page size — prevents limit=10000 DoS
MAX_PAGE_SIZE = 200


def serialize_order(o) -> dict:
    """Serialize order to JSON-safe dict. Never raises."""
    def _val(v):
        from enum import Enum as _Enum
        if v is None:                        return None
        if isinstance(v, bool):              return v
        if isinstance(v, _Enum):             return str(v.value)   # BEFORE str — fixes OrderStatus(str,Enum)
        if isinstance(v, int):               return v
        if isinstance(v, float):             return v
        if isinstance(v, str):               return v
        if hasattr(v, "isoformat"):          return v.isoformat()
        return str(v)

    # Prefer reading attributes directly (avoids lazy-load issues)
    fields = [
        "id","property_id","host_id","host_name","host_phone",
        "cleaner_id","cleaner_name","price","checkout_time",
        "assigned_at","arrived_at","completed_at","created_at","updated_at",
        "status","version","text_notes","voice_url","completion_photos",
        "accepted_by_host",
    ]
    result = {}
    for f in fields:
        try:
            result[f] = _val(getattr(o, f, None))
        except Exception:
            result[f] = None
    return result


router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    property_id:  int
    price:        float
    checkout_time: str
    host_id:      int | None = None
    host_name:    str | None = None
    host_phone:   str | None = None
    text_notes:   str | None = None

    @field_validator("price")
    @classmethod
    def price_positive(cls, v):
        if v < 0:
            raise ValueError("price must be non-negative")
        return v

    @field_validator("text_notes")
    @classmethod
    def notes_length(cls, v):
        if v and len(v) > 2000:
            raise ValueError("text_notes too long")
        return v


class AcceptOrderRequest(BaseModel):
    cleaner_id:   int
    cleaner_name: str | None = None


class UpdateOrderRequest(BaseModel):
    """Whitelist — only these fields may be updated by clients."""
    status:             str | None = None
    completion_photos:  str | None = None
    text_notes:         str | None = None
    checkout_time:      str | None = None
    accepted_by_host:   int | None = None
    voice_url:          str | None = None


# ── List orders (public read) ─────────────────────────────────────────────────

@router.get("")
async def list_orders(
    status:      str   = "open",
    limit:       int   = 50,
    offset:      int   = 0,
    cleaner_lat: float = None,
    cleaner_lon: float = None,
    db: AsyncSession   = Depends(get_db),
):
    """訂單列表 — 公開讀取（含緩存）"""
    # FIX: hard-cap page size — prevents limit=10000 DoS
    limit = min(limit, MAX_PAGE_SIZE)

    ck = cache_key("orders", status=status, limit=limit, offset=offset,
                   clat=cleaner_lat, clon=cleaner_lon)
    cached = await get_from_cache(ck)
    if cached is not None:
        return cached

    query = select(Order, Property).outerjoin(Property, Order.property_id == Property.id)
    if status and status != "all":
        query = query.where(Order.status == status)

    total = await db.scalar(
        (select(func.count(Order.id)).where(Order.status == status)
         if status and status != "all"
         else select(func.count(Order.id)))
    ) or 0

    query = query.order_by(Order.created_at.desc()).limit(limit).offset(offset)
    rows  = (await db.execute(query)).all()

    order_list = []
    for row in rows:
        o, prop = row[0], row[1] if len(row) > 1 else None
        od = serialize_order(o)
        if prop:
            od["property_name"]    = prop.name
            od["property_address"] = prop.address
            if prop.host_phone:
                od["host_phone"]   = prop.host_phone
            if prop.latitude:
                od["property_lat"] = prop.latitude
                od["property_lng"] = prop.longitude
                if cleaner_lat and cleaner_lon:
                    from app.core.geo import geo_service
                    dist = await geo_service.calculate_distance(
                        cleaner_lat, cleaner_lon, prop.latitude, prop.longitude
                    )
                    if dist is not None:
                        od["distance_km"] = round(dist, 1)
        order_list.append(od)

    resp = {"success": True, "data": order_list,
            "pagination": {"total": total, "limit": limit, "offset": offset,
                           "has_more": offset + len(order_list) < total}}
    await set_cache(ck, resp, ttl_l1=5, ttl_l2=30)
    return resp


@router.get("/cleaner/{cleaner_id}")
async def get_cleaner_orders(
    cleaner_id: int,
    limit:  int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Depends(require_cleaner),   # ← auth
):
    """清潔員自己的訂單（需認證）"""
    # FIX: cleaner can only see their own orders
    if token.user_id != cleaner_id:
        raise HTTPException(status_code=403, detail="只能查看自己的訂單")

    limit = min(limit, MAX_PAGE_SIZE)
    ck = cache_key("cleaner_orders", cleaner_id=cleaner_id, limit=limit, offset=offset)
    cached = await get_from_cache(ck)
    if cached is not None:
        return success_response(data=cached)

    query = (
        select(Order, Property)
        .outerjoin(Property, Order.property_id == Property.id)
        .where(Order.cleaner_id == cleaner_id)
        .where(Order.status != OrderStatus.OPEN)
        .order_by(Order.created_at.desc())
        .limit(limit).offset(offset)
    )
    rows = (await db.execute(query)).all()

    order_list = []
    for row in rows:
        o, prop = row[0], row[1] if len(row) > 1 else None
        od = serialize_order(o)
        if prop:
            od["property_name"]    = prop.name
            od["property_address"] = prop.address
        order_list.append(od)

    await set_cache(ck, order_list, ttl_l1=2, ttl_l2=5)
    return success_response(data=order_list)


# ── Create order (host only) ──────────────────────────────────────────────────

@router.post("")
async def create_order(
    req: CreateOrderRequest,
    db:  AsyncSession = Depends(get_db),
    token: TokenData  = Depends(require_host),    # ← auth
):
    """創建訂單（需要房東認證）"""
    checkout_time = None
    if req.checkout_time:
        try:
            checkout_time = datetime.fromisoformat(req.checkout_time.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="退房時間格式錯誤")

    # Duplicate order guard
    if req.property_id and checkout_time:
        dup = await db.execute(
            select(Order).where(
                Order.property_id == req.property_id,
                Order.checkout_time == checkout_time,
                Order.status == OrderStatus.OPEN,
            )
        )
        if dup.first():
            raise HTTPException(status_code=400, detail="該房源在此時間已有未完成訂單")

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

    order_data = serialize_order(order)

    await manager.broadcast("orders", {"type": "new_order", "data": order_data})
    await delete_pattern("orders:*")
    await delete_pattern("cleaner_orders:*")

    try:
        from app.core.accept_script import order_script
        await order_script.sync_order_to_redis(order_data)
    except Exception as exc:
        logger.warning("Redis order sync failed: %s", exc)

    # Fetch property for geo dispatch
    prop_result = await db.execute(select(Property).where(Property.id == req.property_id))
    prop = prop_result.scalar_one_or_none()

    try:
        from app.core.worker import get_worker_pool
        pool = await get_worker_pool()
        if prop and prop.latitude and prop.longitude:
            await pool.enqueue_in(30,  "order_tasks.expand_order_search", order.id, 5,  10)
            await pool.enqueue_in(60,  "order_tasks.expand_order_search", order.id, 10, 20)
            await pool.enqueue_in(120, "order_tasks.cancel_order",        order.id, "timeout")
    except Exception as exc:
        logger.warning("Task enqueue failed: %s", exc)

    try:
        if prop and prop.latitude and prop.longitude:
            from app.core.geo import geo_service
            nearby = await geo_service.get_nearby_cleaners(
                lat=prop.latitude, lon=prop.longitude, radius_km=10, limit=20)
            if nearby:
                await manager.dispatch_to_cleaners(
                    cleaner_ids=[c["id"] for c in nearby],
                    order_data=order_data,
                    require_ack=True,
                )
    except Exception as exc:
        logger.warning("Geo dispatch failed: %s", exc)

    return success_response(data=order_data, message="訂單創建成功")


# ── Accept order (cleaner only) ───────────────────────────────────────────────

@router.post("/{order_id}/accept")
async def accept_order(
    order_id: int,
    req: AcceptOrderRequest,
    db:  AsyncSession = Depends(get_db),
    token: TokenData  = Depends(require_cleaner),  # ← auth
):
    """搶單（清潔員認證 + 悲觀鎖）"""
    # FIX: cleaner can only accept on behalf of themselves
    if token.user_id != req.cleaner_id:
        raise HTTPException(status_code=403, detail="只能以自己身份接單")

    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update(skip_locked=True)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在或已被鎖定")
    if order.status != OrderStatus.OPEN:
        raise HTTPException(status_code=400, detail="訂單已被搶走")

    order.status      = OrderStatus.ACCEPTED
    order.cleaner_id  = req.cleaner_id
    order.cleaner_name= req.cleaner_name
    order.assigned_at = datetime.utcnow()
    order.updated_at  = datetime.utcnow()
    order.version    += 1
    await db.commit()
    await db.refresh(order)

    order_data = serialize_order(order)
    await manager.broadcast("orders", {"type": "order_accepted",
        "data": {"order_id": order_id, "cleaner_id": req.cleaner_id, "order": order_data}})
    await manager.notify_order_taken(order_id, req.cleaner_id)
    await delete_pattern("orders:*")
    await delete_pattern("cleaner_orders:*")

    return success_response(message="搶單成功")


# ── Update order (auth required) ─────────────────────────────────────────────

@router.patch("/{order_id}")
@router.put("/{order_id}")
async def update_order(
    order_id: int,
    req:  UpdateOrderRequest,
    db:   AsyncSession = Depends(get_db),
    token: TokenData   = Depends(get_current_user),
):
    """更新訂單 — 完全防崩潰版本"""
    import logging
    log = logging.getLogger(__name__)

    try:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order  = result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="訂單不存在")

        if token.user_type == "cleaner" and order.cleaner_id != token.user_id:
            raise HTTPException(status_code=403, detail="無權修改此訂單")

        updates = req.model_dump(exclude_unset=True)

        # ── status ────────────────────────────────────────────
        if "status" in updates and updates["status"]:
            try:
                order.status = OrderStatus(updates["status"])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"無效狀態: {updates['status']}")
            if updates["status"] == "arrived":
                order.arrived_at = datetime.utcnow()
            elif updates["status"] == "completed":
                order.completed_at = datetime.utcnow()

        # ── text fields ───────────────────────────────────────
        for field in ("completion_photos", "text_notes", "voice_url"):
            if field in updates:
                setattr(order, field, updates[field])

        # ── checkout_time: string → datetime ──────────────────
        if "checkout_time" in updates and updates["checkout_time"]:
            ct = updates["checkout_time"]
            if isinstance(ct, str):
                ct = ct.strip().replace("Z", "+00:00")
                # Handle "2025-01-15T10:00" (no seconds) and full ISO
                try:
                    order.checkout_time = datetime.fromisoformat(ct)
                except ValueError:
                    raise HTTPException(status_code=400, detail="退房時間格式錯誤，請使用 ISO 格式")
            else:
                order.checkout_time = ct

        # ── accepted_by_host ──────────────────────────────────
        if "accepted_by_host" in updates:
            order.accepted_by_host = bool(updates["accepted_by_host"])

        order.updated_at = datetime.utcnow()
        await db.commit()

        # Re-query (avoid async refresh issues)
        result2 = await db.execute(select(Order).where(Order.id == order_id))
        order = result2.scalar_one()

    except HTTPException:
        raise
    except Exception as exc:
        log.error("update_order %d failed: %s", order_id, exc, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失敗: {type(exc).__name__}: {exc}")

    try:
        await delete_pattern("orders:*")
        await delete_pattern("cleaner_orders:*")
        await manager.broadcast("orders", {"type": "order_updated", "data": serialize_order(order)})
    except Exception as exc:
        log.warning("post-update side effects failed: %s", exc)

    return success_response(data=serialize_order(order))


@router.get("/{order_id}")
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    """訂單詳情（公開讀取）"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order  = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    return success_response(data=serialize_order(order))


@router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    db:   AsyncSession = Depends(get_db),
    token: TokenData   = Depends(require_host),     # ← auth
):
    """刪除訂單（房東認證）"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order  = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")

    # FIX: host can only delete their own orders
    if order.host_id and order.host_id != token.user_id:
        raise HTTPException(status_code=403, detail="無權刪除此訂單")

    await db.delete(order)
    await db.commit()
    await delete_pattern("orders:*")
    return success_response(message="刪除成功")


# ── WebSocket ────────────────────────────────────────────────────────────────

@router.websocket("/ws/orders")
@router.websocket("/ws/orders/{cleaner_id}")
async def websocket_orders(websocket: WebSocket, cleaner_id: int = None):
    """訂單即時 WebSocket"""
    await manager.connect(websocket, "orders", cleaner_id=cleaner_id)
    try:
        import json
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data) if data != "ping" else {"type": "ping"}
            except Exception:
                msg = {"type": "unknown"}
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg.get("type") == "ack":
                mid = msg.get("message_id")
                if mid:
                    await manager.handle_ack(mid)
    except WebSocketDisconnect:
        manager.disconnect(websocket, "orders")
