"""
認證 API
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.database import get_db
from app.core.response import success_response, error_response
from app.models.models import Cleaner, User
from pydantic import BaseModel

router = APIRouter()
settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# --- Schema ---
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
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


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


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """註冊"""
    # 檢查手機是否已存在
    result = await db.execute(
        select(Cleaner).where(Cleaner.phone == req.phone)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="手機號已註冊")
    
    # 創建用戶
    if req.user_type == "cleaner":
        user = Cleaner(
            name=req.name,
            phone=req.phone,
            password_hash=get_password_hash(req.password),
        )
    else:
        user = User(
            name=req.name,
            phone=req.phone,
            password_hash=get_password_hash(req.password),
        )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return success_response(data={"id": user.id}, message="註冊成功")
