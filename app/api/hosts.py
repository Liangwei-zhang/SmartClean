"""
Hosts API - 房東管理
"""
from fastapi import APIRouter, Body, Depends, Query, HTTPException
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
        "code": getattr(u, "code", None),
    } for u in users])


@router.get("/code/{code}")
async def verify_host_code(code: str, db: AsyncSession = Depends(get_db)):
    """通過驗證碼獲取房東信息"""
    result = await db.execute(
        select(User).where(User.code == code)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="驗證碼錯誤")

    return success_response(data={
        "id": user.id,
        "name": user.name,
        "phone": user.phone,
        "code": user.code,
    })


@router.get("/{host_id}")
async def get_host(host_id: int, db: AsyncSession = Depends(get_db)):
    """獲取房東詳情"""
    result = await db.execute(
        select(User).where(User.id == host_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="房東不存在")

    return success_response(data={
        "id": user.id,
        "name": user.name,
        "phone": user.phone,
        "code": user.code,
    })


@router.post("")
async def create_host(
    name: str = Body(None),
    phone: str = Body(None),
    db: AsyncSession = Depends(get_db)
):
    """新增房東"""
    if not name or not phone:
        raise HTTPException(status_code=400, detail="名稱和電話必填")
    
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=6))
    
    # 臨時使用簡單哈希
    password_hash = f"temp_{code}"
    user = User(name=name, phone=phone, code=code, password_hash=password_hash)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return success_response(data={"id": user.id, "code": code}, message="新增成功")


@router.put("/{host_id}")
async def update_host(
    host_id: int,
    name: str = Body(None),
    phone: str = Body(None),
    db: AsyncSession = Depends(get_db)
):
    """更新房東"""
    result = await db.execute(
        select(User).where(User.id == host_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="房東不存在")
    
    if name:
        user.name = name
    if phone:
        user.phone = phone
    
    await db.commit()
    await db.refresh(user)
    
    return success_response(data={"id": user.id, "name": user.name, "phone": user.phone}, message="更新成功")


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
