"""
兩級快取系統 (L1 內存 + L2 Redis) + 防擊穿
"""
import json
import hashlib
from functools import wraps
from typing import TypeVar, Callable, Any
import asyncio
from cachetools import TTLCache
import redis.asyncio as redis

from app.core.config import get_settings
from app.core.websocket import get_redis

T = TypeVar('T')

settings = get_settings()

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
    
    # L2: Redis
    r = await get_redis()
    value = await r.get(key)
    if value:
        data = json.loads(value)
        # 回填 L1
        l1_cache[key] = data
        return data
    
    return None


async def set_cache(key: str, value: Any, ttl_l1: int = 5, ttl_l2: int = 300):
    """設置兩級快取"""
    # L1
    l1_cache[key] = value
    
    # L2
    r = await get_redis()
    await r.setex(key, ttl_l2, json.dumps(value))


async def delete_cache(key: str):
    """刪除快取"""
    # L1
    l1_cache.pop(key, None)
    
    # L2
    r = await get_redis()
    await r.delete(key)


async def delete_pattern(pattern: str):
    """刪除匹配的所有快取"""
    # L1
    keys_to_delete = [k for k in l1_cache.keys() if pattern in k]
    for k in keys_to_delete:
        l1_cache.pop(k, None)
    
    # L2
    r = await get_redis()
    async for key in r.scan_iter(match=pattern):
        await r.delete(key)


# --- 防擊穿裝飾器 ---
_lock_cache = {}


async def cache_with_lock(key: str, fetch_func: Callable, ttl: int = 300):
    """
    防擊穿快取
    多個請求同時訪問時，只有一個會去數據庫更新快取
    """
    # 嘗試獲取
    cached = await get_from_cache(key)
    if cached is not None:
        return cached
    
    # 檢查是否已有其他請求在 fetch
    if key in _lock_cache:
        # 等待其他請求完成
        for _ in range(50):  # 最多等 5 秒
            await asyncio.sleep(0.1)
            cached = await get_from_cache(key)
            if cached is not None:
                return cached
    
    # 獲取鎖
    _lock_cache[key] = True
    try:
        # 從數據庫獲取
        data = await fetch_func()
        # 設置快取
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
