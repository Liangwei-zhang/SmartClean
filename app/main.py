"""
SmartClean - 核彈級優化版清潔服務平台
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.core.response import ORJSONResponse
from app.core.websocket import get_redis


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命周期"""
    # 啟動
    await init_db()
    
    # 測試 Redis 連接
    try:
        r = await get_redis()
        await r.ping()
        print("✅ Redis 連接成功")
    except Exception as e:
        print(f"⚠️ Redis 連接失敗: {e}")
    
    print("🚀 SmartClean 引擎啟動 (ORJSON + Granian + Redis)")
    yield
    # 關閉
    print("🛑 SmartClean 引擎關閉")


# 創建應用
app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    default_response_class=ORJSONResponse,  # 全域 ORJSON
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "SmartClean API", "version": "2.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# 路由
from app.api import orders, auth
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
