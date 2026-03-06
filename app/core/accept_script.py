"""
Redis Lua 腳本 - 搶單原子操作
實現萬級/秒併發搶單
"""
import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()

# Lua 腳本：原子搶單
# 邏輯: 先檢查訂單狀態，設置鎖，更新狀態在一個原子操作中完成
ACCEPT_ORDER_SCRIPT = """
-- 參數: order_id, cleaner_id, max_retries
local order_id = tonumber(ARGV[1])
local cleaner_id = tonumber(ARGV[2])
local max_retries = tonumber(ARGV[3])

-- 搶單鎖 key
local lock_key = 'lock:order:' .. order_id

-- 嘗試獲取分佈式鎖 (100ms 過期)
local lock_acquired = redis.call('SET', lock_key, cleaner_id, 'PX', 100, 'NX')
if not lock_acquired then
    return {err = 'LOCKED'}
end

-- 檢查訂單狀態
local order_status = redis.call('HGET', 'order:' .. order_id, 'status')
if order_status ~= 'open' then
    redis.call('DEL', lock_key)
    return {err = 'NOT_OPEN', status = order_status}
end

-- 原子更新訂單狀態 (使用 Lua 保證原子性)
local updated = redis.call('HSET', 'order:' .. order_id, 'status', 'accepted', 'cleaner_id', cleaner_id, 'assigned_at', ARGV[4])
redis.call('DEL', lock_key)

if updated > 0 then
    return {ok = 'SUCCESS', order_id = order_id, cleaner_id = cleaner_id}
else
    return {err = 'UPDATE_FAILED'}
end
"""

# Lua 腳本：批量檢查多個訂單狀態
CHECK_ORDERS_SCRIPT = """
local order_ids = cjson.decode(ARGV[1])
local results = {}

for i, order_id in ipairs(order_ids) do
    local status = redis.call('HGET', 'order:' .. order_id, 'status')
    table.insert(results, {order_id = order_id, status = status or 'unknown'})
end

return cjson.encode(results)
"""


class RedisOrderScript:
    """Redis Lua 搶單腳本封裝"""
    
    def __init__(self):
        self._script_sha = None
        self._check_sha = None
    
    async def get_client(self):
        r = await redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        return r
    
    async def init_scripts(self, r: redis.Redis):
        """初始化腳本"""
        if not self._script_sha:
            self._script_sha = await r.script_load(ACCEPT_ORDER_SCRIPT)
        if not self._check_sha:
            self._check_sha = await r.script_load(CHECK_ORDERS_SCRIPT)
        return self._script_sha, self._check_sha
    
    async def try_accept_order(
        self, 
        order_id: int, 
        cleaner_id: int,
        max_retries: int = 3
    ) -> dict:
        """
        嘗試搶單 (Redis Lua 原子操作)
        
        Returns:
            {ok: 'SUCCESS', order_id, cleaner_id} 或 {err: '原因'}
        """
        r = await self.get_client()
        await self.init_scripts(r)
        
        import time
        timestamp = str(int(time.time() * 1000))
        
        try:
            # 執行 Lua 腳本
            result = await r.evalsha(
                self._script_sha,
                0,  # key count
                order_id, cleaner_id, max_retries, timestamp
            )
            
            if isinstance(result, dict) and result.get('err'):
                return result
            
            return {'ok': 'SUCCESS', 'order_id': order_id, 'cleaner_id': cleaner_id}
            
        except Exception as e:
            return {'err': str(e)}
    
    async def sync_order_to_redis(self, order_data: dict) -> bool:
        """將訂單同步到 Redis Hash (搶單前必須調用)"""
        r = await self.get_client()
        
        order_id = order_data.get('id')
        if not order_id:
            return False
        
        key = f"order:{order_id}"
        
        # 使用 HSET 存儲訂單核心字段
        await r.hset(key, mapping={
            'id': str(order_id),
            'status': order_data.get('status', 'open'),
            'property_id': str(order_data.get('property_id', '')),
            'price': str(order_data.get('price', 0)),
            'created_at': str(order_data.get('created_at', ''))
        })
        
        # 設置 TTL (24小時過期)
        await r.expire(key, 86400)
        
        return True
    
    async def bulk_check_status(self, order_ids: list[int]) -> list[dict]:
        """批量檢查訂單狀態"""
        r = await self.get_client()
        await self.init_scripts(r)
        
        import json
        ids_json = json.dumps([str(oid) for oid in order_ids])
        
        result = await r.evalsha(
            self._check_sha,
            0,
            ids_json
        )
        
        return json.loads(result) if result else []


# 全局實例
order_script = RedisOrderScript()
