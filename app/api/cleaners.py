"""
清潔工 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlmodel import func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Cleaner
from app.core.websocket import manager

router = APIRouter()


class LocationUpdate(BaseModel):
    latitude: float
    longitude: float


class CleanerStatusUpdate(BaseModel):
    status: str  # online/offline/busy


@router.get("")
async def list_cleaners(
    status: str = None,
    db: AsyncSession = Depends(get_db)
):
    """清潔工列表"""
    query = select(Cleaner)
    if status:
        query = query.where(Cleaner.status == status)
    query = query.order_by(Cleaner.rating.desc())
    
    result = await db.execute(query)
    cleaners = result.scalars().all()
    
    return success_response(data=[c.model_dump() for c in cleaners])


@router.get("/{cleaner_id}")
async def get_cleaner(cleaner_id: int, db: AsyncSession = Depends(get_db)):
    """清潔工詳情"""
    result = await db.execute(
        select(Cleaner).where(Cleaner.id == cleaner_id)
    )
    cleaner = result.scalar_one_or_none()
    
    if not cleaner:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    
    return success_response(data=cleaner.model_dump())


@router.patch("/{cleaner_id}/location")
async def update_location(
    cleaner_id: int,
    req: LocationUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新清潔工位置"""
    result = await db.execute(
        update(Cleaner)
        .where(Cleaner.id == cleaner_id)
        .values(
            latitude=req.latitude,
            longitude=req.longitude,
            last_location_update=func.now()
        )
    )
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    
    # 廣播位置更新
    await manager.broadcast("cleaners", {
        "type": "location_update",
        "cleaner_id": cleaner_id,
        "latitude": req.latitude,
        "longitude": req.longitude
    })
    
    return success_response(message="位置更新成功")


@router.patch("/{cleaner_id}/status")
async def update_status(
    cleaner_id: int,
    req: CleanerStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新清潔工在線狀態"""
    valid_statuses = ["online", "offline", "busy"]
    if req.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"狀態必須是: {valid_statuses}")
    
    result = await db.execute(
        update(Cleaner)
        .where(Cleaner.id == cleaner_id)
        .values(status=req.status)
    )
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    
    # 廣播狀態更新
    await manager.broadcast("cleaners", {
        "type": "status_update",
        "cleaner_id": cleaner_id,
        "status": req.status
    })
    
    return success_response(message="狀態更新成功")


@router.get("/{cleaner_id}/stats")
async def get_cleaner_stats(cleaner_id: int, db: AsyncSession = Depends(get_db)):
    """清潔工統計"""
    result = await db.execute(
        select(Cleaner).where(Cleaner.id == cleaner_id)
    )
    cleaner = result.scalar_one_or_none()
    
    if not cleaner:
        raise HTTPException(status_code=404, detail="清潔工不存在")
    
    return success_response(data={
        "total_jobs": cleaner.total_jobs,
        "accepted_jobs": cleaner.accepted_jobs,
        "rating": cleaner.rating,
        "status": cleaner.status
    })
