"""清潔工 API — 需要認證"""
import logging
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlmodel import func
from pydantic import BaseModel

from app.core.auth     import require_cleaner, require_admin, get_current_user, optional_user, TokenData
from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Cleaner
from app.core.websocket import manager

logger = logging.getLogger(__name__)
router = APIRouter()


class LocationUpdate(BaseModel):
    latitude:  float
    longitude: float

class CleanerStatusUpdate(BaseModel):
    status: str


@router.post("")
async def create_cleaner(
    name:     str = Body(...),
    phone:    str = Body(...),
    password: str = Body(...),
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(require_admin),     # ← admin only
):
    import random, string, bcrypt
    chars = string.ascii_uppercase + string.digits
    code  = "".join(random.choices(chars, k=6))
    pw    = bcrypt.hashpw(password[:72].encode(), bcrypt.gensalt()).decode()
    c = Cleaner(name=name, phone=phone, code=code, password_hash=pw)
    db.add(c); await db.commit(); await db.refresh(c)
    return success_response(data={"id": c.id, "code": code}, message="新增成功")


@router.get("")
async def list_cleaners(status: str = None, db: AsyncSession = Depends(get_db),
                        token: TokenData | None = Depends(optional_user)):
    # Public: anyone can list cleaners (needed for code-based login lookup)
    # password_hash is always stripped
    query = select(Cleaner)
    if status:
        query = query.where(Cleaner.status == status)
    query = query.order_by(Cleaner.rating.desc())
    cleaners = (await db.execute(query)).scalars().all()
    # FIX: strip password_hash from response
    return success_response(data=[{k: v for k, v in c.model_dump().items() if k != "password_hash"} for c in cleaners])


@router.get("/{cleaner_id}")
async def get_cleaner(cleaner_id: int, db: AsyncSession = Depends(get_db),
                      token: TokenData = Depends(get_current_user)):
    # Cleaners can see themselves; admins can see all
    if token.user_type == "cleaner" and token.user_id != cleaner_id:
        raise HTTPException(status_code=403, detail="無權查看")
    result  = await db.execute(select(Cleaner).where(Cleaner.id == cleaner_id))
    cleaner = result.scalar_one_or_none()
    if not cleaner:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    data = {k: v for k, v in cleaner.model_dump().items() if k != "password_hash"}
    return success_response(data=data)


@router.patch("/{cleaner_id}/location")
async def update_location(
    cleaner_id: int,
    req: LocationUpdate,
    db:  AsyncSession = Depends(get_db),
    token: TokenData  = Depends(require_cleaner),
):
    if token.user_id != cleaner_id:
        raise HTTPException(status_code=403, detail="只能更新自己的位置")
    result = await db.execute(
        update(Cleaner).where(Cleaner.id == cleaner_id)
        .values(latitude=req.latitude, longitude=req.longitude,
                last_location_update=func.now(), updated_at=func.now())
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    # Also update Redis GEO index
    try:
        from app.core.geo import geo_service
        await geo_service.update_cleaner_location(cleaner_id, req.latitude, req.longitude)
    except Exception as exc:
        logger.warning("GEO update failed: %s", exc)
    await manager.broadcast("cleaners", {"type": "location_update",
        "cleaner_id": cleaner_id, "latitude": req.latitude, "longitude": req.longitude})
    return success_response(message="位置更新成功")


@router.patch("/{cleaner_id}/status")
async def update_status(
    cleaner_id: int,
    req: CleanerStatusUpdate,
    db:  AsyncSession = Depends(get_db),
    token: TokenData  = Depends(require_cleaner),
):
    if token.user_id != cleaner_id:
        raise HTTPException(status_code=403, detail="只能更新自己的狀態")
    valid = ["online", "offline", "busy"]
    if req.status not in valid:
        raise HTTPException(status_code=400, detail=f"狀態必須是: {valid}")
    result = await db.execute(
        update(Cleaner).where(Cleaner.id == cleaner_id)
        .values(status=req.status, updated_at=func.now())
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    await manager.broadcast("cleaners", {"type": "status_update",
        "cleaner_id": cleaner_id, "status": req.status})
    return success_response(message="狀態更新成功")


@router.get("/{cleaner_id}/stats")
async def get_cleaner_stats(cleaner_id: int, db: AsyncSession = Depends(get_db),
                             token: TokenData = Depends(get_current_user)):
    if token.user_type == "cleaner" and token.user_id != cleaner_id:
        raise HTTPException(status_code=403, detail="無權查看")
    result  = await db.execute(select(Cleaner).where(Cleaner.id == cleaner_id))
    cleaner = result.scalar_one_or_none()
    if not cleaner:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    return success_response(data={"total_jobs": cleaner.total_jobs,
        "accepted_jobs": cleaner.accepted_jobs, "rating": cleaner.rating, "status": cleaner.status})


@router.put("/{cleaner_id}")
async def update_cleaner(
    cleaner_id: int,
    name:  str = Body(None),
    phone: str = Body(None),
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(require_admin),
):
    result  = await db.execute(select(Cleaner).where(Cleaner.id == cleaner_id))
    cleaner = result.scalar_one_or_none()
    if not cleaner:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    if name:  cleaner.name  = name
    if phone: cleaner.phone = phone
    await db.commit(); await db.refresh(cleaner)
    return success_response(data={"id": cleaner.id}, message="更新成功")


@router.delete("/{cleaner_id}")
async def delete_cleaner(cleaner_id: int, db: AsyncSession = Depends(get_db),
                          _: TokenData = Depends(require_admin)):
    from app.models.models import Order
    from sqlalchemy import update as sqla_update
    await db.execute(sqla_update(Order).where(Order.cleaner_id == cleaner_id)
                     .values(cleaner_id=None, cleaner_name=None))
    result  = await db.execute(select(Cleaner).where(Cleaner.id == cleaner_id))
    cleaner = result.scalar_one_or_none()
    if not cleaner:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    await db.delete(cleaner); await db.commit()
    return success_response(message="刪除成功")
