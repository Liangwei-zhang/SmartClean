"""
速率限制 — 純 Redis 滑動視窗 (移除 asyncio.Lock 序列化瓶頸)
100 萬日活架構：每個 IP 獨立計數，不共用全局鎖
"""
import time
import logging
from fastapi import Request, HTTPException

from app.core.websocket import get_redis

logger = logging.getLogger(__name__)

LIMIT_WINDOW    = 60        # 60 秒滑動視窗
DEFAULT_LIMIT   = 1000      # 預設每分鐘 1000 次
LOGIN_LIMIT     = 20        # 登入端點更嚴格
UPLOAD_LIMIT    = 100       # 上傳端點


async def check_rate_limit(request: Request, key: str = None, limit: int = DEFAULT_LIMIT) -> bool:
    """
    純 Redis 滑動視窗限流，無本地鎖，線性可擴展。
    返回 True = 允許, False = 拒絕
    """
    client_ip = request.client.host if request.client else "unknown"
    rkey = f"rl:{key or client_ip}"

    r = await get_redis()
    if not r:
        return True   # Redis 不可用時放行（降級策略）

    try:
        now      = int(time.time() * 1000)   # ms
        window   = LIMIT_WINDOW * 1000
        pipe     = r.pipeline(transaction=False)
        pipe.zremrangebyscore(rkey, 0, now - window)
        pipe.zcard(rkey)
        pipe.zadd(rkey, {str(now): now})
        pipe.expire(rkey, LIMIT_WINDOW + 5)
        results  = await pipe.execute()
        count    = results[1]                # count BEFORE this request
        return count < limit
    except Exception as exc:
        logger.warning("Rate limit Redis error: %s", exc)
        return True   # 降級放行


async def rate_limit_dep(request: Request, limit: int = DEFAULT_LIMIT) -> None:
    """Dependency: raises 429 if over limit."""
    if not await check_rate_limit(request, limit=limit):
        raise HTTPException(status_code=429, detail="請求過於頻繁，請稍後再試")


# ── Blacklist ─────────────────────────────────────────────────────────────────

async def check_blacklist(request: Request) -> bool:
    r = await get_redis()
    if not r:
        return False
    try:
        ip = request.client.host if request.client else "unknown"
        return await r.get(f"blacklist:{ip}") is not None
    except Exception as exc:
        logger.warning("Blacklist check error: %s", exc)
        return False


async def add_to_blacklist(ip: str, reason: str = "manual", ttl: int = 86400 * 30) -> None:
    r = await get_redis()
    if r:
        try:
            await r.setex(f"blacklist:{ip}", ttl, reason)
        except Exception as exc:
            logger.error("Blacklist add error: %s", exc)


async def remove_from_blacklist(ip: str) -> None:
    r = await get_redis()
    if r:
        try:
            await r.delete(f"blacklist:{ip}")
        except Exception as exc:
            logger.error("Blacklist remove error: %s", exc)


async def get_rate_limit_stats() -> dict:
    r = await get_redis()
    if not r:
        return {}
    try:
        keys = await r.keys("rl:*")
        return {"active_keys": len(keys), "window_seconds": LIMIT_WINDOW, "default_limit": DEFAULT_LIMIT}
    except Exception:
        return {}
