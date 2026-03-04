"""
SmartClean - 核彈級優化版清潔服務平台
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.database import init_db
from app.core.response import ORJSONResponse
from app.core.websocket import get_redis, manager

logger = logging.getLogger(__name__)


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
        logger.info("✅ Redis 連接成功")
    except Exception as e:
        logger.warning(f"⚠️ Redis 連接失敗: {e}")
    
    logger.info("🚀 SmartClean 引擎啟動 (ORJSON + Granian + Redis)")
    yield
    # 關閉
    logger.info("🛑 SmartClean 引擎關閉")


# 創建應用
app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    default_response_class=ORJSONResponse,
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
    return FileResponse("static/cleaner.html")


@app.get("/index.html")
async def index_html():
    return FileResponse("static/cleaner.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# 靜態文件
import os
upload_dir = settings.UPLOAD_DIR
os.makedirs(f"{upload_dir}/images", exist_ok=True)
os.makedirs(f"{upload_dir}/voices", exist_ok=True)

app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 前端頁面路由
from fastapi.responses import FileResponse


@app.get("/")
async def index_page():
    return FileResponse("static/cleaner.html")


@app.get("/cleaner")
async def cleaner_page():
    return FileResponse("static/cleaner.html")


@app.get("/host")
async def host_page():
    return FileResponse("static/host.html")


@app.get("/admin")
async def admin_page():
    return FileResponse("static/admin.html")


# 路由
from app.api import orders, auth, properties, cleaners, order_status, upload, notifications
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(cleaners.router, prefix="/api/cleaners", tags=["Cleaners"])
app.include_router(order_status.router, prefix="/api/orders", tags=["Order Status"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])

from app.api import stats
app.include_router(stats.router, prefix="/api/stats", tags=["Stats"])

# WebSocket
from app.api.orders import websocket_orders
app.add_api_websocket_route("/api/orders/ws/orders", websocket_orders)
