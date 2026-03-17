"""
冪等性 Key - 防止重複請求
確保同一個請求只會被處理一次
"""
import asyncio
import hashlib
import time
from fastapi import Request, HTTPException
from functools import wraps

from app.core.websocket import get_redis

# 冪等性 Key 過期時間 (24小時)
IDEMPOTENCY_TTL = 86400


async def check_idempotency(request: Request, key_header: str = "Idempotency-Key") -> str | None:
    """
    檢查並返回冪等性 Key
    若 Key 已存在，返回之前緩存的響應字符串
    若 Key 不存在，返回 Key 本身
    若 Header 缺失，返回 None
    """
    idempotency_key = request.headers.get(key_header)
    if not idempotency_key:
        return None

    r = await get_redis()
    if not r:
        return idempotency_key

    try:
        exists = await r.get(f"idempotency:{idempotency_key}")
        if exists:
            return exists
    except Exception:
        pass

    return idempotency_key


async def save_idempotency(key: str, response_data: str):
    """保存冪等性 Key 和響應"""
    r = await get_redis()
    if not r:
        return
    try:
        await r.setex(f"idempotency:{key}", IDEMPOTENCY_TTL, response_data)
    except Exception:
        pass


def idempotency_required(func):
    """裝飾器：強制要求 Idempotency Key"""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            raise HTTPException(
                status_code=400,
                detail="Idempotency-Key header is required"
            )
        return await func(request, *args, **kwargs)
    return wrapper


async def process_with_idempotency(request: Request, process_func):
    """
    處理請求並實現冪等性
    用於: 創建訂單、支付等關鍵操作
    """
    key = request.headers.get("Idempotency-Key")
    if not key:
        key = hashlib.sha256(
            f"{request.url}:{time.time()}".encode()
        ).hexdigest()[:32]

    r = await get_redis()
    if not r:
        return await process_func()

    lock_key = f"idempotency:lock:{key}"
    try:
        lock = await r.set(lock_key, "1", nx=True, ex=10)
    except Exception:
        return await process_func()

    if not lock:
        # FIX: import asyncio at top of file, not at bottom
        for _ in range(50):
            await asyncio.sleep(0.1)
            try:
                result = await r.get(f"idempotency:{key}")
                if result:
                    raise HTTPException(status_code=409, detail="請求處理中，請稍後再試")
            except HTTPException:
                raise
            except Exception:
                break

    try:
        result = await process_func()
        try:
            await r.setex(f"idempotency:{key}", IDEMPOTENCY_TTL, str(result))
        except Exception:
            pass
        return result
    finally:
        try:
            await r.delete(lock_key)
        except Exception:
            pass
