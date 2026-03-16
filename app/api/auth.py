"""
認證 API
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional
import bcrypt

from app.core.config import get_settings
from app.core.websocket import get_redis

async def generate_unique_code(db: AsyncSession, user_type: str) -> str:
    """生成唯一邀請碼"""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=8))
        # 檢查是否存在
        if user_type == "cleaner":
            result = await db.execute(select(Cleaner).where(Cleaner.code == code))
        else:
            result = await db.execute(select(User).where(User.code == code))
        if not result.scalar_one_or_none():
            return code


async def is_token_revoked(token: str) -> bool:
    """檢查 Token 是否已被撤銷"""
    r = await get_redis()
    if r:
        try:
            revoked = await r.get(f"token_revoked:{token}")
            return revoked is not None
        except:
            pass
    return False


async def revoke_token(token: str) -> bool:
    """撤銷 Token (加入黑名單)"""
    r = await get_redis()
    if r:
        try:
            # 解析 token 獲取過期時間
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                exp = payload.get("exp", 0)
                ttl = max(exp - int(datetime.utcnow().timestamp()), 60)
            except:
                ttl = 60 * 24 * 7  # 默認7天
            
            await r.setex(f"token_revoked:{token}", ttl, "1")
            return True
        except:
            pass
    return False

from app.core.database import get_db
from app.core.response import success_response, error_response
from app.models.models import Cleaner, User
from pydantic import BaseModel

router = APIRouter()
settings = get_settings()
security = HTTPBearer()

# 直接使用 bcrypt 避免 passlib 兼容性問題
import bcrypt

def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt 限制 72 字符
    try:
        return bcrypt.checkpw(plain[:72].encode(), hashed.encode())
    except:
        return False

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password[:72].encode(), bcrypt.gensalt()).decode()

class LoginRequest(BaseModel):
    phone: str
    password: str
    user_type: str = "cleaner"  # cleaner / host


class RegisterRequest(BaseModel):
    name: str
    phone: str
    password: str
    user_type: str = "cleaner"


def create_access_token(data: dict) -> str:
    """創建 JWT Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt 限制 72 字符
    try:
        return bcrypt.checkpw(plain[:72].encode(), hashed.encode())
    except:
        return False


def get_password_hash(password: str) -> str:
    # bcrypt 限制 72 字符
    return bcrypt.hashpw(password[:72].encode(), bcrypt.gensalt()).decode()


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登入"""
    # 根據類型查詢
    if req.user_type == "cleaner":
        result = await db.execute(
            select(Cleaner).where(Cleaner.phone == req.phone)
        )
        user = result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(User).where(User.phone == req.phone)
        )
        user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="用戶不存在")
    
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="密碼錯誤")
    
    # 生成 Token
    token = create_access_token({
        "sub": str(user.id),
        "type": req.user_type
    })
    
    return success_response(data={
        "token": token,
        "user_id": user.id,
        "user_type": req.user_type,
        "name": user.name
    })


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """登出 (撤銷 Token)"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少認證信息")
    
    token = authorization.replace("Bearer ", "")
    
    # 撤銷 token
    revoked = await revoke_token(token)
    
    if revoked:
        return success_response(message="登出成功")
    else:
        return success_response(message="Token 已失效")


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """註冊"""
    # 檢查手機是否已存在
    result = await db.execute(
        select(Cleaner).where(Cleaner.phone == req.phone)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="手機號已註冊")
    
    # 生成唯一邀請碼
    code = await generate_unique_code(db, req.user_type)
    
    # 創建用戶
    if req.user_type == "cleaner":
        user = Cleaner(
            name=req.name,
            phone=req.phone,
            password_hash=get_password_hash(req.password),
            code=code,
        )
    else:
        user = User(
            name=req.name,
            phone=req.phone,
            password_hash=get_password_hash(req.password),
            code=code,
        )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return success_response(data={"id": user.id, "code": code}, message="註冊成功")
