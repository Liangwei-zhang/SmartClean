"""房源 API — 寫操作需要房東認證"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth     import require_host, get_current_user, TokenData
from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Property
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class PropertyCreate(BaseModel):
    name: str; address: str
    street: str | None = None; city: str | None = None
    province: str | None = None; house_number: str | None = None
    postal_code: str | None = None; latitude: float | None = None
    longitude: float | None = None; bedrooms: int = 1; bathrooms: int = 1
    floor: int | None = None; area: float | None = None
    host_id: int | None = None; host_phone: str | None = None
    cleaning_time_minutes: int = 60; notes: str | None = None


class PropertyUpdate(BaseModel):
    name: str | None = None; address: str | None = None
    street: str | None = None; city: str | None = None
    province: str | None = None; house_number: str | None = None
    postal_code: str | None = None; latitude: float | None = None
    longitude: float | None = None; bedrooms: int | None = None
    bathrooms: int | None = None; floor: int | None = None
    area: float | None = None; cleaning_time_minutes: int | None = None
    status: str | None = None; notes: str | None = None


@router.get("")
async def list_properties(host_id: int = None, status: str = "active",
                           db: AsyncSession = Depends(get_db)):
    query = select(Property)
    if host_id: query = query.where(Property.host_id == host_id)
    if status:  query = query.where(Property.status == status)
    query = query.order_by(Property.created_at.desc())
    props = (await db.execute(query)).scalars().all()
    return success_response(data=[p.model_dump() for p in props])


@router.post("")
async def create_property(req: PropertyCreate, db: AsyncSession = Depends(get_db),
                           token: TokenData = Depends(require_host)):
    prop = Property(**req.model_dump())
    db.add(prop); await db.commit(); await db.refresh(prop)
    return success_response(data=prop.model_dump(), message="房源創建成功")


@router.get("/{property_id}")
async def get_property(property_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop   = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="房源不存在")
    return success_response(data=prop.model_dump())


@router.patch("/{property_id}")
@router.put("/{property_id}")
async def update_property(property_id: int, req: PropertyUpdate,
                           db: AsyncSession = Depends(get_db),
                           token: TokenData = Depends(require_host)):
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop   = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="房源不存在")
    # FIX: ownership check
    if prop.host_id and prop.host_id != token.user_id:
        raise HTTPException(status_code=403, detail="無權修改此房源")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    await db.commit(); await db.refresh(prop)
    return success_response(data=prop.model_dump(), message="更新成功")


@router.delete("/{property_id}")
async def delete_property(property_id: int, db: AsyncSession = Depends(get_db),
                           token: TokenData = Depends(require_host)):
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop   = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="房源不存在")
    if prop.host_id and prop.host_id != token.user_id:
        raise HTTPException(status_code=403, detail="無權刪除此房源")
    prop.status = "inactive"
    await db.commit()
    return success_response(message="刪除成功")
