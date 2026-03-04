"""
房源 API - Property CRUD
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlmodel import func
import os
import uuid

from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Property
from app.core.config import get_settings
from pydantic import BaseModel

router = APIRouter()
settings = get_settings()


class PropertyCreate(BaseModel):
    name: str
    address: str
    street: str | None = None
    city: str | None = None
    province: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    bedrooms: int = 1
    bathrooms: int = 1
    floor: int | None = None
    area: float | None = None
    host_id: int | None = None
    host_phone: str | None = None
    cleaning_time_minutes: int = 60
    notes: str | None = None


class PropertyUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    street: str | None = None
    city: str | None = None
    province: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floor: int | None = None
    area: float | None = None
    cleaning_time_minutes: int | None = None
    status: str | None = None
    notes: str | None = None


@router.get("")
async def list_properties(
    host_id: int = None,
    status: str = "active",
    db: AsyncSession = Depends(get_db)
):
    """房源列表"""
    query = select(Property)
    if host_id:
        query = query.where(Property.host_id == host_id)
    if status:
        query = query.where(Property.status == status)
    query = query.order_by(Property.created_at.desc())
    
    result = await db.execute(query)
    properties = result.scalars().all()
    
    return success_response(data=[p.model_dump() for p in properties])


@router.post("")
async def create_property(
    req: PropertyCreate,
    db: AsyncSession = Depends(get_db)
):
    """創建房源"""
    prop = Property(**req.model_dump())
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    
    return success_response(data=prop.model_dump(), message="房源創建成功")


@router.get("/{property_id}")
async def get_property(property_id: int, db: AsyncSession = Depends(get_db)):
    """房源詳情"""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    
    if not prop:
        raise HTTPException(status_code=404, detail="房源不存在")
    
    return success_response(data=prop.model_dump())


@router.patch("/{property_id}")
@router.patch("/{property_id}")
@router.put("/{property_id}")
async def update_property(
    property_id: int,
    req: PropertyUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新房源"""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    
    if not prop:
        raise HTTPException(status_code=404, detail="房源不存在")
    
    # 更新字段
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    
    await db.commit()
    await db.refresh(prop)
    
    return success_response(data=prop.model_dump(), message="更新成功")


@router.delete("/{property_id}")
async def delete_property(property_id: int, db: AsyncSession = Depends(get_db)):
    """刪除房源 (軟刪除)"""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    
    if not prop:
        raise HTTPException(status_code=404, detail="房源不存在")
    
    prop.status = "inactive"
    await db.commit()
    
    return success_response(message="刪除成功")


# PUT is same as PATCH
update_property_put = update_property
