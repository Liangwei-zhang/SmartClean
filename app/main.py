"""
SmartClean — Production-ready server
"""
import logging
import os
import time
from contextlib import asynccontextmanager

logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.core.config    import get_settings
from app.core.database  import init_db
from app.core.response  import ORJSONResponse
from app.core.websocket import get_redis
from app.core.monitoring import log_request, Metrics, logger

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    r = await get_redis()
    if r:
        try:
            await r.ping()
            logger.info("✅ Redis connected")
        except Exception as exc:
            logger.warning("⚠️  Redis ping failed: %s", exc)
    else:
        logger.warning("⚠️  Redis unavailable — running in degraded mode")
    logger.info("🚀 SmartClean started")
    yield
    logger.info("🛑 SmartClean shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version="3.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/docs"       if settings.DEBUG else None,
    redoc_url="/redoc"     if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# ── Global exception handler — always returns JSON, never plain text ──────────
from fastapi import Request as _Request
from fastapi.responses import JSONResponse as _JSONResponse
import traceback as _tb

@app.exception_handler(Exception)
async def global_exception_handler(request: _Request, exc: Exception):
    import logging
    logging.getLogger("smartclean").error(
        "Unhandled %s on %s %s: %s",
        type(exc).__name__, request.method, request.url.path, exc
    )
    # Always return JSON so frontend can parse it
    return _JSONResponse(
        status_code=500,
        content={"success": False, "detail": f"{type(exc).__name__}: {exc}"}
    )

@app.exception_handler(500)
async def http_500_handler(request: _Request, exc):
    return _JSONResponse(
        status_code=500,
        content={"success": False, "detail": "Internal server error"}
    )


# CORS
cors_origins = ["http://localhost:3000", "http://localhost:8080"]
if settings.CORS_ORIGINS:
    cors_origins.extend([o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Request middleware ────────────────────────────────────────────────────────
from app.core.rate_limit import check_rate_limit, check_blacklist, LOGIN_LIMIT, UPLOAD_LIMIT

# FIX: exact path sets — /api/auth/login-by-code must NOT share the login rate limit
LOGIN_PATHS  = {"/api/auth/login"}          # exact match only
UPLOAD_PATHS = {"/api/upload/image", "/api/upload/voice"}


@app.middleware("http")
async def gate_requests(request: Request, call_next):
    # 1. Blacklist
    if await check_blacklist(request):
        return JSONResponse(status_code=403, content={"detail": "Access denied"})

    # 2. Rate limiting — FIX: use exact path for login, prefix for upload, generous for others
    path = request.url.path
    if path in LOGIN_PATHS:
        limit = LOGIN_LIMIT          # 20/min — strict brute-force protection
    elif path.startswith("/api/upload"):
        limit = UPLOAD_LIMIT         # 100/min
    elif path.startswith("/api/"):
        limit = 2000                 # 2000/min per IP — generous for normal use
    else:
        limit = None

    if limit and not await check_rate_limit(request, limit=limit):
        return JSONResponse(status_code=429, content={"detail": "請求過於頻繁，請稍後再試"})

    # 3. Metrics
    t0       = time.monotonic()
    response = await call_next(request)
    log_request(endpoint=path, duration=time.monotonic() - t0,
                status=response.status_code, method=request.method)
    return response


# ── Static files ──────────────────────────────────────────────────────────────
upload_dir = settings.UPLOAD_DIR
os.makedirs(f"{upload_dir}/images", exist_ok=True)
os.makedirs(f"{upload_dir}/voices", exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")
app.mount("/static",  StaticFiles(directory="static"),   name="static")



VERSION = "5"

@app.get("/")
@app.get("/index.html")
async def root(v: str = None):
    if v != VERSION:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/?v={VERSION}", status_code=302)
    return FileResponse("static/index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})

@app.get("/cleaner")
@app.get("/cleaner.html")
async def cleaner_page(v: str = None):
    if v != VERSION:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/cleaner?v={VERSION}", status_code=302)
    return FileResponse("static/cleaner.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})

@app.get("/host")
@app.get("/host.html")
async def host_page(v: str = None):
    if v != VERSION:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/host?v={VERSION}", status_code=302)
    return FileResponse("static/host.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})

@app.get("/admin")
@app.get("/admin.html")
async def admin_page(v: str = None):
    if v != VERSION:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/admin?v={VERSION}", status_code=302)
    return FileResponse("static/admin.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})

@app.get("/stats")
async def stats_page(v: str = None):
    if v != VERSION:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/stats?v={VERSION}", status_code=302)
    return FileResponse("static/stats.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})


# ── API routers# ── API routers ───────────────────────────────────────────────────────────────
from app.api import orders, auth, hosts, properties, cleaners, order_status
from app.api import upload, notifications, stats, geocode, geo_search
from app.api.monitoring import router as monitoring_router

app.include_router(orders.router,        prefix="/api/orders",        tags=["Orders"])
app.include_router(auth.router,          prefix="/api/auth",          tags=["Auth"])
app.include_router(properties.router,    prefix="/api/properties",    tags=["Properties"])
app.include_router(cleaners.router,      prefix="/api/cleaners",      tags=["Cleaners"])
app.include_router(order_status.router,  prefix="/api/orders",        tags=["Order Status"])
app.include_router(upload.router,        prefix="/api/upload",        tags=["Upload"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(stats.router,         prefix="/api/stats",         tags=["Stats"])
app.include_router(geocode.router,       prefix="/api",               tags=["Geocode"])
app.include_router(geo_search.router,    prefix="/api/geo",           tags=["Geo Search"])
app.include_router(hosts.router,         prefix="/api/hosts",         tags=["Hosts"])
app.include_router(monitoring_router,    prefix="/api/monitoring",    tags=["Monitoring"])
