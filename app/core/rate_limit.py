"""
速率限制 - 防止 API 濫用 (優化版)
"""
import time
from fastapi import Request, HTTPException
from collections import defaultdict
import threading

from app.core.websocket import get_redis


# 內存限流 (快速攔截)
memory_limits = defaultdict(list)
lock = threading.Lock()
LIMIT_WINDOW = 60  # 60秒窗口
DEFAULT_LIMIT = 1000  # 默認每分鐘1000次 (壓測友好)


def _cleanup_expired(client_times, now):
    """清理過期的記錄"""
    return [t for t in client_times if now - t < LIMIT_WINDOW]


async def check_rate_limit(
    request: Request,
    key: str = None,
    limit: int = DEFAULT_LIMIT
) -> bool:
    """
    檢查速率限制
    返回 True = 允許訪問
    返回 False = 超過限制
    """
    # 使用 IP 或用戶 ID 作為 key
    if not key:
        key = request.client.host if request.client else "unknown"
    
    now = time.time()
    
    # 內存快速檢查 (線程安全)
    with lock:
        client_times = memory_limits.get(key, [])
        # 清理過期的
        client_times = _cleanup_expired(client_times, now)
        
        if len(client_times) >= limit:
            # Redis 記錄違規 (異步，不阻塞)
            try:
                r = await get_redis()
                if r:
                    await r.incr(f"rate_limit:violation:{key}")
            except:
                pass
            return False
        
        client_times.append(now)
        memory_limits[key] = client_times
    
    return True


async def rate_limit(
    request: Request,
    limit: int = DEFAULT_LIMIT,
    message: str = "請求過於頻繁，請稍後再試"
):
    """速率限制裝飾器"""
    allowed = await check_rate_limit(request, limit=limit)
    if not allowed:
        raise HTTPException(status_code=429, detail=message)


# --- 黑白名單 ---
async def check_blacklist(request: Request) -> bool:
    """檢查是否在黑名單"""
    try:
        r = await get_redis()
        if r:
            ip = request.client.host if request.client else "unknown"
            blocked = await r.get(f"blacklist:{ip}")
            return blocked is not None
    except:
        pass
    return False


async def add_to_blacklist(ip: str, reason: str = "manual"):
    """添加到黑名單"""
    try:
        r = await get_redis()
        if r:
            await r.setex(f"blacklist:{ip}", 86400 * 30, reason)  # 30天
    except:
        pass


async def remove_from_blacklist(ip: str):
    """從黑名單移除"""
    try:
        r = await get_redis()
        if r:
            await r.delete(f"blacklist:{ip}")
    except:
        pass


def get_rate_limit_stats() -> dict:
    """獲取限流統計"""
    with lock:
        now = time.time()
        total = sum(len(_cleanup_expired(times, now)) for times in memory_limits.values())
        return {
            "active_ips": len(memory_limits),
            "total_requests": total,
            "window_seconds": LIMIT_WINDOW,
            "default_limit": DEFAULT_LIMIT
        }
