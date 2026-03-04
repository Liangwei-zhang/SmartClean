"""
Hosts API - 房東管理
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.response import success_response
from app.models.models import User

router = APIRouter()


@router.get("")
@router.post("")
async def create_host(
    name: str = Query(...),
    phone: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """新增房東"""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=6))
    
    from passlib.hash import bcrypt
    user = User(name=name, phone=phone, code=code, password_hash=bcrypt.hash("123456"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return success_response(data={"id": user.id, "code": code}, message="新增成功")
async def list_hosts(db: AsyncSession = Depends(get_db)):
    """房東列表"""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return success_response(data=[{
        "id": u.id,
        "name": u.name,
        "phone": u.phone,
        
    } for u in users])
