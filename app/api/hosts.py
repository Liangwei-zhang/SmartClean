"""房東 API — 需要認證"""
import logging
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.auth     import require_host, require_admin, get_current_user, TokenData
from app.core.database import get_db
from app.core.response import success_response
from app.models.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

def _safe(u):
    return {"id": u.id, "name": u.name, "phone": u.phone, "code": u.code}


@router.get("")
async def list_hosts(db: AsyncSession = Depends(get_db), _: TokenData = Depends(require_admin)):
    result = await db.execute(select(User))
    return success_response(data=[_safe(u) for u in result.scalars().all()])


@router.get("/code/{code}")
async def verify_host_code(code: str, db: AsyncSession = Depends(get_db)):
    """登入用 — 公開（用驗證碼驗身）"""
    result = await db.execute(select(User).where(User.code == code))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="驗證碼錯誤")
    return success_response(data=_safe(user))


@router.get("/{host_id}")
async def get_host(host_id: int, db: AsyncSession = Depends(get_db),
                   token: TokenData = Depends(get_current_user)):
    if token.user_type == "host" and token.user_id != host_id:
        raise HTTPException(status_code=403, detail="無權查看")
    result = await db.execute(select(User).where(User.id == host_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="房東不存在")
    return success_response(data=_safe(user))


@router.post("")
async def create_host(
    name:     str = Body(...),
    phone:    str = Body(...),
    password: str = Body(...),
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(require_admin),
):
    import bcrypt, random, string
    chars = string.ascii_uppercase + string.digits
    code  = "".join(random.choices(chars, k=6))
    pw    = bcrypt.hashpw(password[:72].encode(), bcrypt.gensalt()).decode()
    user  = User(name=name, phone=phone, code=code, password_hash=pw)
    db.add(user); await db.commit(); await db.refresh(user)
    return success_response(data={"id": user.id, "code": code}, message="新增成功")


@router.put("/{host_id}")
async def update_host(
    host_id: int,
    name:  str = Body(None),
    phone: str = Body(None),
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == host_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="房東不存在")
    if name:  user.name  = name
    if phone: user.phone = phone
    await db.commit(); await db.refresh(user)
    return success_response(data=_safe(user), message="更新成功")


@router.delete("/{host_id}")
async def delete_host(host_id: int, db: AsyncSession = Depends(get_db),
                       _: TokenData = Depends(require_admin)):
    from app.models.models import Order, Property
    from sqlalchemy import update as sqla_update
    await db.execute(sqla_update(Property).where(Property.host_id == host_id).values(host_id=None))
    await db.execute(sqla_update(Order).where(Order.host_id == host_id)
                     .values(host_id=None, host_name=None, host_phone=None))
    result = await db.execute(select(User).where(User.id == host_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="房東不存在")
    await db.delete(user); await db.commit()
    return success_response(message="刪除成功")
