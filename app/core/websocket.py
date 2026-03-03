"""
Redis 連接 + WebSocket 管理
"""
import redis.asyncio as redis
from fastapi import WebSocket
from typing import Dict, Set, List
import json
import asyncio

from app.core.config import get_settings

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


# WebSocket 連接管理
class ConnectionManager:
    """WebSocket 連接管理器 + Redis Pub/Sub"""
    
    def __init__(self):
        # 訂單頻道訂閱者
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.pubsub = None
        self.pubsub_task = None
    
    async def connect(self, websocket: WebSocket, channel: str = "orders"):
        """客戶端連接"""
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)
        
        # 首次連接，啟動 Pub/Sub 監聽
        if len(self.active_connections[channel]) == 1:
            await self.start_listening(channel)
    
    def disconnect(self, websocket: WebSocket, channel: str = "orders"):
        """客戶端斷開"""
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)
            if not self.active_connections[channel]:
                asyncio.create_task(self.stop_listening(channel))
    
    async def broadcast(self, channel: str, message: dict):
        """廣播消息到所有客戶端 + Redis"""
        r = await get_redis()
        
        # 1. 發給本地 WebSocket 客戶端
        if channel in self.active_connections:
            disconnected = set()
            for websocket in self.active_connections[channel]:
                try:
                    await websocket.send_json(message)
                except:
                    disconnected.add(websocket)
            
            # 清理斷開的連接
            for ws in disconnected:
                self.active_connections[channel].discard(ws)
        
        # 2. 發到 Redis 頻道 (跨節點廣播)
        await r.publish(channel, json.dumps(message))
    
    async def start_listening(self, channel: str):
        """啟動 Redis 訂閱"""
        r = await get_redis()
        self.pubsub = r.pubsub()
        await self.pubsub.subscribe(channel)
        
        # 啟動監聽任務
        async def listen():
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        if channel in self.active_connections:
                            for ws in list(self.active_connections[channel]):
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
