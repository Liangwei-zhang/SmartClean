"""
Hosts API - 房東管理
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
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


@router.post("")
async def create_host(
    name: str = Query(None),
    phone: str = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """新增房東"""
    if not name or not phone:
        raise HTTPException(status_code=400, detail="名稱和電話必填")
    
    import random
    import string
    from passlib.hash import bcrypt
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=6))
    
    user = User(name=name, phone=phone, code=code, password_hash=bcrypt.hash("123456"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return success_response(data={"id": user.id, "code": code}, message="新增成功")


@router.delete("/{host_id}")
async def delete_host(
    host_id: int,
    db: AsyncSession = Depends(get_db)
):
    """刪除房東"""
    from app.models.models import Order
    # 先清除房源
    from app.models.models import Property
    await db.execute(
        update(Property).where(Property.host_id == host_id).values(host_id=None)
    )
    # 先清除訂單
    await db.execute(
        update(Order).where(Order.host_id == host_id).values(host_id=None, host_name=None, host_phone=None)
    )
    
    result = await db.execute(
        select(User).where(User.id == host_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="房東不存在")
    
    await db.delete(user)
    await db.commit()
    
    return success_response(message="刪除成功")
