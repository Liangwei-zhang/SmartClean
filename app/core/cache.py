"""
兩級快取系統 (L1 內存 + L2 Redis) + 防擊穿
"""
import json
import hashlib
from functools import wraps
from typing import TypeVar, Callable, Any
import asyncio
from cachetools import TTLCache

from app.core.websocket import get_redis

T = TypeVar('T')

# L1 快取 - 內存 (5秒 TTL)
l1_cache = TTLCache(maxsize=1000, ttl=5)


def cache_key(prefix: str, **kwargs) -> str:
    """生成快取鍵"""
    key_data = json.dumps(kwargs, sort_keys=True)
    key_hash = hashlib.md5(key_data.encode()).hexdigest()[:12]
    return f"{prefix}:{key_hash}"


async def get_from_cache(key: str) -> Any | None:
    """從兩級快取獲取"""
    # L1: 內存
    if key in l1_cache:
        return l1_cache[key]

    # L2: Redis (FIX: guard against None redis)
    r = await get_redis()
    if not r:
        return None

    try:
        value = await r.get(key)
        if value:
            data = json.loads(value)
            l1_cache[key] = data
            return data
    except Exception:
        pass

    return None


async def set_cache(key: str, value: Any, ttl_l1: int = 5, ttl_l2: int = 300):
    """設置兩級快取"""
    # L1
    l1_cache[key] = value

    # L2 (FIX: guard against None redis)
    r = await get_redis()
    if not r:
        return

    try:
        await r.setex(key, ttl_l2, json.dumps(value, default=str))
    except Exception:
        pass


async def delete_cache(key: str):
    """刪除快取"""
    l1_cache.pop(key, None)

    r = await get_redis()
    if not r:
        return
    try:
        await r.delete(key)
    except Exception:
        pass


async def delete_pattern(pattern: str):
    """刪除匹配的所有快取"""
    # L1
    keys_to_delete = [k for k in list(l1_cache.keys()) if pattern.rstrip("*") in k]
    for k in keys_to_delete:
        l1_cache.pop(k, None)

    # L2 (FIX: guard against None redis)
    r = await get_redis()
    if not r:
        return
    try:
        async for key in r.scan_iter(match=pattern):
            await r.delete(key)
    except Exception:
        pass


# --- 防擊穿裝飾器 ---
_lock_cache: dict = {}


async def cache_with_lock(key: str, fetch_func: Callable, ttl: int = 300):
    """
    防擊穿快取
    多個請求同時訪問時，只有一個會去數據庫更新快取
    """
    cached = await get_from_cache(key)
    if cached is not None:
        return cached

    if key in _lock_cache:
        for _ in range(50):  # 最多等 5 秒
            await asyncio.sleep(0.1)
            cached = await get_from_cache(key)
            if cached is not None:
                return cached

    _lock_cache[key] = True
    try:
        data = await fetch_func()
        await set_cache(key, data, ttl_l2=ttl)
        return data
    finally:
        _lock_cache.pop(key, None)


def cached(key_prefix: str, ttl: int = 300):
    """裝飾器版本"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = cache_key(key_prefix, args=str(args), kwargs=str(sorted(kwargs.items())))
            return await cache_with_lock(key, lambda: func(*args, **kwargs), ttl)
        return wrapper
    return decorator
