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


async def get_redis() -> redis.Redis:
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
    """
    WebSocket 連接管理器 - 支持分散式派單
    
    架構:
    ┌─────────────────────────────────────────────────────────────┐
    │                     Redis Pub/Sub                         │
    │  Channel: "order_dispatch"                                 │
    │  Channel: "order_status"                                  │
    └─────────────────────────────────────────────────────────────┘
           ▲                  ▲                   ▲
           │                  │                   │
    ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐
    │  Worker 1   │    │  Worker 2   │    │  Worker 3   │
    │  ┌────────┐ │    │  ┌────────┐ │    │  ┌────────┐ │
    │  │ WS池   │ │    │  │ WS池   │ │    │  │ WS池   │ │
    │  │ (按ID) │ │    │  │ (按ID) │ │    │  │ (按ID) │ │
    │  └────────┘ │    │  └────────┘ │    │  └────────┘ │
    └─────────────┘    └─────────────┘    └─────────────┘
    """
    
    def __init__(self):
        # 頻道 -> WebSocket 集合 (用於廣播)
        self.channel_connections: Dict[str, Set[WebSocket]] = {}
        
        # 清潔員 ID -> WebSocket (用於精準派單)
        self.cleaner_connections: Dict[int, WebSocket] = {}
        
        # WebSocket -> 清潔員 ID 映射
        self.ws_to_cleaner: Dict[WebSocket, int] = {}
        
        # 全局 Pub/Sub 客戶端
        self.pubsub = None
        self.pubsub_task = None
        
        # 已確認的推送 (用於 ACK)
        self.pending_acks: Dict[str, asyncio.Task] = {}
    
    async def connect(
        self, 
        websocket: WebSocket, 
        channel: str = "orders",
        cleaner_id: int = None
    ):
        """客戶端連接"""
        await websocket.accept()
        
        # 添加到頻道
        if channel not in self.channel_connections:
            self.channel_connections[channel] = set()
        self.channel_connections[channel].add(websocket)
        
        # 如果是清潔員，建立 ID 映射
        if cleaner_id:
            self.cleaner_connections[cleaner_id] = websocket
            self.ws_to_cleaner[websocket] = cleaner_id
        
        Metrics.record_ws_connect()
        
        # 首次連接，啟動 Pub/Sub 監聽
        if len(self.channel_connections.get(channel, [])) == 1:
            await self.start_listening(channel)
    
    def disconnect(
        self, 
        websocket: WebSocket, 
        channel: str = "orders"
    ):
        """客戶端斷開"""
        # 從頻道移除
        if channel in self.channel_connections:
            self.channel_connections[channel].discard(websocket)
            
            # 如果頻道沒人了，停止監聽
            if not self.channel_connections[channel]:
                asyncio.create_task(self.stop_listening(channel))
        
        # 從清潔員映射移除
        cleaner_id = self.ws_to_cleaner.pop(websocket, None)
        if cleaner_id:
            self.cleaner_connections.pop(cleaner_id, None)
    
    async def broadcast(self, channel: str, message: dict):
        """廣播消息到所有客戶端 + Redis"""
        r = await get_redis()
        
        # 1. 發給本地 WebSocket 客戶端
        if channel in self.channel_connections:
            disconnected = set()
            for ws in self.channel_connections[channel]:
                try:
                    await ws.send_json(message)
                except:
                    disconnected.add(ws)
            
            for ws in disconnected:
                self.channel_connections[channel].discard(ws)
        
        # 2. 發到 Redis 頻道 (跨節點廣播)
        await r.publish(channel, json.dumps(message))
    
    async def dispatch_to_cleaners(
        self, 
        cleaner_ids: list[int], 
        order_data: dict,
        require_ack: bool = True
    ):
        """
        定向派單到指定清潔員
        
        Args:
            cleaner_ids: 目標清潔員 ID 列表
            order_data: 訂單數據
            require_ack: 是否需要 ACK 確認
        """
        r = await get_redis()
        
        # 準備消息
        message = {
            "type": "order_dispatch",
            "order": order_data,
            "message_id": f"msg_{order_data.get('id')}_{asyncio.get_event_loop().time()}"
        }
        
        # 本地推送
        local_targets = []
        for cleaner_id in cleaner_ids:
            ws = self.cleaner_connections.get(cleaner_id)
            if ws:
                try:
                    await ws.send_json(message)
                    local_targets.append(cleaner_id)
                except:
                    # 推送失敗，從映射中移除
                    self.cleaner_connections.pop(cleaner_id, None)
        
        # 發布到 Redis (讓其他 Worker 也推送)
        await r.publish("order_dispatch", json.dumps({
            "target_ids": cleaner_ids,
            "message": message
        }))
        
        # 如果需要 ACK，設置超時等待
        if require_ack:
            msg_id = message["message_id"]
            # 5秒後檢查 ACK，沒收到則重試或發短信
            asyncio.create_task(self._check_ack_timeout(msg_id, cleaner_ids, message))
        
        return local_targets
    
    async def notify_order_taken(self, order_id: int, cleaner_id: int):
        """
        通知其他清潔員訂單已被搶走
        """
        r = await get_redis()
        
        message = {
            "type": "order_taken",
            "order_id": order_id,
            "taken_by": cleaner_id
        }
        
        # 本地廣播
        if "orders" in self.channel_connections:
            for ws in self.channel_connections["orders"]:
                try:
                    await ws.send_json(message)
                except:
                    pass
        
        # 發布到 Redis
        await r.publish("order_dispatch", json.dumps({
            "broadcast": True,
            "message": message
        }))
    
    async def handle_ack(self, message_id: str):
        """處理 ACK 確認"""
        # 取消等待
        task = self.pending_acks.pop(message_id, None)
        if task:
            task.cancel()
    
    async def _check_ack_timeout(
        self, 
        message_id: str, 
        target_ids: list[int],
        message: dict
    ):
        """檢查 ACK 超時 (5秒)"""
        await asyncio.sleep(5)
        
        if message_id in self.pending_acks:
            # 沒收到 ACK，記錄日誌
            print(f"⚠️ 訂單 {message.get('order', {}).get('id')} 推送未確認")
            # TODO: 這裡可以觸發短信/推送通知重試
    
    async def start_listening(self, channel: str):
        """啟動 Redis 訂閱"""
        r = await get_redis()
        self.pubsub = r.pubsub()
        await self.pubsub.subscribe(channel)
        
        async def listen():
            async for msg in self.pubsub.listen():
                if msg["type"] == "message":
                    try:
                        data = json.loads(msg["data"])
                        
                        # 記錄Metrics
                        Metrics.record_ws_message()
                        
                        # 處理定向派單
                        if channel == "order_dispatch":
                            target_ids = data.get("target_ids", [])
                            broadcast = data.get("broadcast", False)
                            dispatch_msg = data.get("message", {})
                            
                            # 定向推送
                            for cleaner_id in target_ids:
                                ws = self.cleaner_connections.get(cleaner_id)
                                if ws:
                                    await ws.send_json(dispatch_msg)
                            
                            # 廣播推送
                            if broadcast and "orders" in self.channel_connections:
                                for ws in list(self.channel_connections["orders"]):
                                    try:
                                        await ws.send_json(data.get("message", {}))
                                    except:
                                        pass
                            
                            continue
                        
                        # 普通廣播
                        if channel in self.channel_connections:
                            for ws in list(self.channel_connections[channel]):
                                try:
                                    await ws.send_json(data)
                                except:
                                    pass
                    except:
                        pass
        
        self.pubsub_task = asyncio.create_task(listen())
    
    async def stop_listening(self, channel: str):
        """停止 Redis 訂閱"""
        if self.pubsub_task:
            self.pubsub_task.cancel()
            self.pubsub_task = None
        if self.pubsub:
            await self.pubsub.unsubscribe(channel)
            await self.pubsub.close()
            self.pubsub = None


# 全局管理器
manager = ConnectionManager()
