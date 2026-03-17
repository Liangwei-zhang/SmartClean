"""
Redis Lua 腳本 — 原子搶單
複用全局 Redis 連接，不再每次 from_url() 建立新連線
"""
import logging
import json
import time
from app.core.websocket import get_redis   # ← 複用全局客戶端

logger = logging.getLogger(__name__)

# Lua 腳本：原子搶單（100ms 鎖過期）
ACCEPT_ORDER_SCRIPT = """
local lock_key = 'lock:order:' .. ARGV[1]
local acquired = redis.call('SET', lock_key, ARGV[2], 'PX', 100, 'NX')
if not acquired then return {err = 'LOCKED'} end
local status = redis.call('HGET', 'order:' .. ARGV[1], 'status')
if status ~= 'open' then
    redis.call('DEL', lock_key)
    return {err = 'NOT_OPEN'}
end
redis.call('HSET', 'order:' .. ARGV[1], 'status', 'accepted', 'cleaner_id', ARGV[2], 'assigned_at', ARGV[3])
redis.call('DEL', lock_key)
return {ok = 'SUCCESS'}
"""

CHECK_ORDERS_SCRIPT = """
local ids = cjson.decode(ARGV[1])
local out = {}
for _, id in ipairs(ids) do
    local s = redis.call('HGET', 'order:' .. id, 'status')
    table.insert(out, {order_id = id, status = s or 'unknown'})
end
return cjson.encode(out)
"""


class RedisOrderScript:
    """FIX: 複用 get_redis() 單例，不再每次新建連接"""

    def __init__(self):
        self._accept_sha: str | None = None
        self._check_sha:  str | None = None

    async def _init_scripts(self):
        r = await get_redis()
        if not r:
            return None
        if not self._accept_sha:
            try:
                self._accept_sha = await r.script_load(ACCEPT_ORDER_SCRIPT)
                self._check_sha  = await r.script_load(CHECK_ORDERS_SCRIPT)
            except Exception as exc:
                logger.error("Failed to load Lua scripts: %s", exc)
                return None
        return r

    async def try_accept_order(self, order_id: int, cleaner_id: int) -> dict:
        """原子搶單。返回 {'ok': 'SUCCESS'} 或 {'err': '...'}"""
        r = await self._init_scripts()
        if not r:
            return {"err": "Redis unavailable"}
        ts = str(int(time.time() * 1000))
        try:
            await r.evalsha(self._accept_sha, 0, order_id, cleaner_id, ts)
            return {"ok": "SUCCESS", "order_id": order_id, "cleaner_id": cleaner_id}
        except Exception as exc:
            logger.warning("accept_order script error: %s", exc)
            return {"err": str(exc)}

    async def sync_order_to_redis(self, order_data: dict) -> bool:
        """將訂單快取到 Redis Hash（創建訂單時呼叫）"""
        r = await get_redis()
        if not r:
            return False
        oid = order_data.get("id")
        if not oid:
            return False
        try:
            await r.hset(f"order:{oid}", mapping={
                "id":          str(oid),
                "status":      order_data.get("status", "open"),
                "property_id": str(order_data.get("property_id", "")),
                "price":       str(order_data.get("price", 0)),
                "created_at":  str(order_data.get("created_at", "")),
            })
            await r.expire(f"order:{oid}", 86400)
            return True
        except Exception as exc:
            logger.error("sync_order_to_redis error: %s", exc)
            return False

    async def bulk_check_status(self, order_ids: list[int]) -> list[dict]:
        r = await self._init_scripts()
        if not r:
            return []
        try:
            result = await r.evalsha(self._check_sha, 0, json.dumps([str(i) for i in order_ids]))
            return json.loads(result) if result else []
        except Exception as exc:
            logger.error("bulk_check_status error: %s", exc)
            return []


order_script = RedisOrderScript()
