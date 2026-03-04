"""
Hosts API - 房東管理
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.response import success_response
from app.models.models import User

router = APIRouter()


@router.get("")
async def list_hosts(db: AsyncSession = Depends(get_db)):
    """房東列表"""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return success_response(data=[{
        "id": u.id,
        "name": u.name,
        "phone": u.phone,
        
    } for u in users])
