"""
速率限制 - 防止 API 濫用
"""
import time
from fastapi import Request, HTTPException
from collections import defaultdict

from app.core.websocket import get_redis


# 內存限流 (快速攔截)
memory_limits = defaultdict(list)
LIMIT_WINDOW = 60  # 60秒窗口
DEFAULT_LIMIT = 100  # 默認每分鐘100次


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
    
    # 內存快速檢查
    client_times = memory_limits[key]
    # 清理過期的
    client_times = [t for t in client_times if now - t < LIMIT_WINDOW]
    
    if len(client_times) >= limit:
        # Redis 記錄違規
        r = await get_redis()
        await r.incr(f"rate_limit:violation:{key}")
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
    r = await get_redis()
    ip = request.client.host if request.client else "unknown"
    
    blocked = await r.get(f"blacklist:{ip}")
    return blocked is not None


async def add_to_blacklist(ip: str, reason: str = "manual"):
    """添加到黑名單"""
    r = await get_redis()
    await r.setex(f"blacklist:{ip}", 86400 * 30, reason)  # 30天


async def remove_from_blacklist(ip: str):
    """從黑名單移除"""
    r = await get_redis()
    await r.delete(f"blacklist:{ip}")
