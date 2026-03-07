"""
SmartClean - 核彈級優化版清潔服務平台
"""
import logging
import os
import time
from contextlib import asynccontextmanager

# 減少 SQLAlchemy 日誌噪音
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import get_settings
from app.core.database import init_db
from app.core.response import ORJSONResponse
from app.core.websocket import get_redis
from app.core.monitoring import log_request, Metrics, logger

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        r = await get_redis()
        await r.ping()
        logger.info("✅ Redis 連接成功")
    except Exception as e:
        logger.warning(f"⚠️ Redis 連接失敗: {e}")
    logger.info("🚀 SmartClean 引擎啟動")
    yield
    logger.info("🛑 SmartClean 引擎關閉")


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 請求監控 Middleware
from app.core.rate_limit import check_rate_limit, check_blacklist

@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    # 檢查黑名單
    if await check_blacklist(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "Access denied"}
        )
    
    # 檢查速率限制 (對於敏感 API)
    sensitive_paths = ["/api/auth/login", "/api/orders", "/api/upload"]
    if any(request.url.path.startswith(p) for p in sensitive_paths):
        # 登入/上傳更嚴格，但允許更高頻率
        limit = 100 if "/auth/login" in request.url.path else 2000
        if not await check_rate_limit(request, limit=limit):
            return JSONResponse(
                status_code=429,
                content={"detail": "請求過於頻繁，請稍後再試"}
            )
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # 記錄請求
    log_request(
        endpoint=request.url.path,
        duration=duration,
        status=response.status_code,
        method=request.method
    )
    
    return response


# 靜態文件
upload_dir = settings.UPLOAD_DIR
os.makedirs(f"{upload_dir}/images", exist_ok=True)
os.makedirs(f"{upload_dir}/voices", exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")


# 頁面路由
@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/index.html")
async def index_html():
    return FileResponse("static/index.html")


@app.get("/cleaner")
async def cleaner_page():
    return FileResponse("static/cleaner.html")


@app.get("/cleaner.html")
async def cleaner_html():
    return FileResponse("static/cleaner.html")


@app.get("/host")
async def host_page():
    return FileResponse("static/host.html")


@app.get("/host.html")
async def host_html():
    return FileResponse("static/host.html")


@app.get("/admin")
async def admin_page():
    return FileResponse("static/admin.html")


@app.get("/admin.html")
async def admin_html():
    return FileResponse("static/admin.html")


@app.get("/stats")
async def stats_page():
    return FileResponse("static/stats.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# API 路由
from app.api import orders, auth, hosts, properties, cleaners, order_status, upload, notifications, stats, geocode, geo_search

app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(cleaners.router, prefix="/api/cleaners", tags=["Cleaners"])
app.include_router(order_status.router, prefix="/api/orders", tags=["Order Status"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(stats.router, prefix="/api/stats", tags=["Stats"])
app.include_router(geocode.router, prefix="/api", tags=["Geocode"])
app.include_router(geo_search.router, prefix="/api/geo", tags=["Geo Search"])
app.include_router(hosts.router, prefix="/api/hosts", tags=["Hosts"])


# === 監控端點 ===
from app.core.monitoring import Metrics, log_event
from app.api.monitoring import router as monitoring_router

app.include_router(monitoring_router, prefix="/api/monitoring", tags=["Monitoring"])

@app.get("/api/monitoring/stats")
async def get_stats():
    """獲取監控統計"""
    return Metrics.get_stats()

@app.post("/api/monitoring/reset")
async def reset_stats():
    """重置統計數據"""
    Metrics.reset()
    return {"message": "Stats reset"}

@app.get("/api/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "timestamp": time.time()}
