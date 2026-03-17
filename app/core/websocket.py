import logging
logger = logging.getLogger(__name__)
"""
Redis 連接 + WebSocket 管理 - 分散式派單版
支持跨 Worker 精準推送到指定清潔員
"""
import redis.asyncio as redis
from fastapi import WebSocket
from typing import Dict, Set, Optional
import json
import asyncio

from app.core.config import get_settings
from app.core.monitoring import Metrics

settings = get_settings()

# Redis 客戶端
redis_client: redis.Redis = None


async def get_redis() -> Optional[redis.Redis]:
    global redis_client
    if redis_client is None:
        try:
            redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        except Exception:
            return None
    return redis_client


class ConnectionManager:
    """WebSocket 連接管理器 - 支持分散式派單"""

    def __init__(self):
        self.channel_connections: Dict[str, Set[WebSocket]] = {}
        self.cleaner_connections: Dict[int, WebSocket] = {}
        self.ws_to_cleaner: Dict[WebSocket, int] = {}
        self.pubsub = None
        self.pubsub_task = None
        self.pending_acks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, channel: str = "orders", cleaner_id: int = None):
        """客戶端連接"""
        await websocket.accept()

        if channel not in self.channel_connections:
            self.channel_connections[channel] = set()
        self.channel_connections[channel].add(websocket)

        if cleaner_id:
            self.cleaner_connections[cleaner_id] = websocket
            self.ws_to_cleaner[websocket] = cleaner_id

        Metrics.record_ws_connect()

        if len(self.channel_connections.get(channel, [])) == 1:
            await self.start_listening(channel)

    def disconnect(self, websocket: WebSocket, channel: str = "orders"):
        """客戶端斷開"""
        if channel in self.channel_connections:
            self.channel_connections[channel].discard(websocket)
            if not self.channel_connections[channel]:
                asyncio.create_task(self.stop_listening(channel))

        cleaner_id = self.ws_to_cleaner.pop(websocket, None)
        if cleaner_id:
            self.cleaner_connections.pop(cleaner_id, None)

    async def broadcast(self, channel: str, message: dict):
        """廣播消息到所有客戶端 + Redis (FIX: guard None redis)"""
        # 1. 發給本地 WebSocket 客戶端
        if channel in self.channel_connections:
            disconnected = set()
            for ws in list(self.channel_connections[channel]):
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.add(ws)
            for ws in disconnected:
                self.channel_connections[channel].discard(ws)

        # 2. 發到 Redis 頻道 (跨節點廣播)
        r = await get_redis()
        if r:
            try:
                await r.publish(channel, json.dumps(message, default=str))
            except Exception as _exc:
                pass  # expected: client disconnected

    async def dispatch_to_cleaners(
        self,
        cleaner_ids: list[int],
        order_data: dict,
        require_ack: bool = True
    ):
        """定向派單到指定清潔員 (FIX: guard None redis)"""
        message = {
            "type": "order_dispatch",
            "order": order_data,
            "message_id": f"msg_{order_data.get('id')}_{asyncio.get_event_loop().time()}"
        }

        # 本地推送
        for cleaner_id in cleaner_ids:
            ws = self.cleaner_connections.get(cleaner_id)
            if ws:
                try:
                    await ws.send_json(message)
                except Exception:
                    self.cleaner_connections.pop(cleaner_id, None)

        # 發布到 Redis
        r = await get_redis()
        if r:
            try:
                await r.publish("order_dispatch", json.dumps({
                    "target_ids": cleaner_ids,
                    "message": message
                }, default=str))
            except Exception as _exc:
                pass  # expected: client disconnected

        if require_ack:
            msg_id = message["message_id"]
            asyncio.create_task(self._check_ack_timeout(msg_id, cleaner_ids, message))

    async def notify_order_taken(self, order_id: int, cleaner_id: int):
        """通知其他清潔員訂單已被搶走"""
        message = {
            "type": "order_taken",
            "order_id": order_id,
            "taken_by": cleaner_id
        }

        if "orders" in self.channel_connections:
            for ws in list(self.channel_connections["orders"]):
                try:
                    await ws.send_json(message)
                except Exception as _exc:
                    pass  # expected: client disconnected

        r = await get_redis()
        if r:
            try:
                await r.publish("order_dispatch", json.dumps({
                    "broadcast": True,
                    "message": message
                }))
            except Exception as _exc:
                pass  # expected: client disconnected

    async def handle_ack(self, message_id: str):
        """處理 ACK 確認"""
        task = self.pending_acks.pop(message_id, None)
        if task:
            task.cancel()

    async def _check_ack_timeout(self, message_id: str, target_ids: list[int], message: dict):
        """檢查 ACK 超時 (5秒)"""
        await asyncio.sleep(5)
        if message_id in self.pending_acks:
            logger.warning("%s", "⚠️ 訂單 {message.get('order', {}).get('id')} 推送未確認")

    async def start_listening(self, channel: str):
        """啟動 Redis 訂閱"""
        r = await get_redis()
        if not r:
            return

        self.pubsub = r.pubsub()
        await self.pubsub.subscribe(channel)

        async def listen():
            async for msg in self.pubsub.listen():
                if msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"])
                        Metrics.record_ws_message()

                        if channel == "order_dispatch":
                            target_ids = data.get("target_ids", [])
                            broadcast = data.get("broadcast", False)
                            dispatch_msg = data.get("message", {})

                            for cid in target_ids:
                                ws = self.cleaner_connections.get(cid)
                                if ws:
                                    await ws.send_json(dispatch_msg)

                            if broadcast and "orders" in self.channel_connections:
                                for ws in list(self.channel_connections["orders"]):
                                    try:
                                        await ws.send_json(data.get("message", {}))
                                    except Exception as _exc:
                                        pass  # expected: client disconnected
                            continue

                        if channel in self.channel_connections:
                            for ws in list(self.channel_connections[channel]):
                                try:
                                    await ws.send_json(data)
                                except Exception as _exc:
                                    pass  # expected: client disconnected
                    except Exception as _exc:
                        pass  # expected: client disconnected

        self.pubsub_task = asyncio.create_task(listen())

    async def stop_listening(self, channel: str):
        """停止 Redis 訂閱"""
        if self.pubsub_task:
            self.pubsub_task.cancel()
            self.pubsub_task = None
        if self.pubsub:
            try:
                await self.pubsub.unsubscribe(channel)
                await self.pubsub.close()
            except Exception as _exc:
                pass  # expected: client disconnected
            self.pubsub = None


# 全局管理器
manager = ConnectionManager()
