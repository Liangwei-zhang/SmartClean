"""
移動端 WebSocket 容錯機制
- 心跳檢測
- 斷線重連
- 消息補發 (Last-Event-ID)
"""
from typing import Dict, Optional, List
import time
import json
from dataclasses import dataclass, field
from app.core.websocket import manager
from app.core.cache import get_redis


@dataclass
class CleanerSession:
    """清潔員會話"""
    cleaner_id: int
    ws_id: str  # WebSocket ID
    connected_at: float = field(default_factory=time.time)
    last_event_id: str = ""  # 最後收到的消息 ID
    last_ping: float = field(default_factory=time.time)
    is_online: bool = True


class MobileFaultTolerance:
    """
    移動端韌性機制
    
    功能:
    - 心跳檢測 (30秒超時)
    - 消息補發 (Last-Event-ID)
    - 離線消息隊列
    """
    
    # Redis Key
    CLEANER_SESSION_KEY = "ws:session:{cleaner_id}"
    CLEANER_QUEUE_KEY = "ws:queue:{cleaner_id}"  # 離線消息隊列
    LAST_EVENT_KEY = "ws:last_event:{cleaner_id}"
    
    # 超時設置
    PING_TIMEOUT = 30  # 30秒無 Ping 視為斷線
    QUEUE_TTL = 120  # 消息隊列保留 2 分鐘
    
    def __init__(self):
        self.sessions: Dict[int, CleanerSession] = {}
    
    async def register_session(
        self, 
        cleaner_id: int, 
        ws_id: str,
        last_event_id: str = ""
    ) -> CleanerSession:
        """註冊新的會話"""
        session = CleanerSession(
            cleaner_id=cleaner_id,
            ws_id=ws_id,
            last_event_id=last_event_id
        )
        self.sessions[cleaner_id] = session
        
        # 同步到 Redis
        r = await get_redis()
        if r:
            await r.hset(
                self.CLEANER_SESSION_KEY.format(cleaner_id=cleaner_id),
                mapping={
                    "ws_id": ws_id,
                    "connected_at": str(session.connected_at),
                    "last_event_id": last_event_id,
                    "is_online": "1"
                }
            )
            await r.expire(self.CLEANER_SESSION_KEY.format(cleaner_id=cleaner_id), 300)
        
        # 如果有 last_event_id，補發期間漏掉的消息
        if last_event_id:
            await self.replay_missed_messages(cleaner_id, last_event_id)
        
        return session
    
    async def update_last_event(self, cleaner_id: int, event_id: str):
        """更新最後收到的事件 ID"""
        if cleaner_id in self.sessions:
            self.sessions[cleaner_id].last_event_id = event_id
        
        # 同步到 Redis
        r = await get_redis()
        if r:
            await r.set(
                self.LAST_EVENT_KEY.format(cleaner_id=cleaner_id),
                event_id,
                ex=self.QUEUE_TTL
            )
    
    async def handle_ping(self, cleaner_id: int) -> bool:
        """處理客戶端 Ping"""
        if cleaner_id in self.sessions:
            self.sessions[cleaner_id].last_ping = time.time()
            
            # 更新 Redis
            r = await get_redis()
            if r:
                await r.hset(
                    self.CLEANER_SESSION_KEY.format(cleaner_id=cleaner_id),
                    "last_ping",
                    str(time.time())
                )
            return True
        return False
    
    async def check_timeouts(self) -> List[int]:
        """檢查超時會話，返回需要斷開的 cleaner_id 列表"""
        now = time.time()
        timeout_ids = []
        
        for cleaner_id, session in self.sessions.items():
            if now - session.last_ping > self.PING_TIMEOUT:
                timeout_ids.append(cleaner_id)
        
        return timeout_ids
    
    async def disconnect_session(self, cleaner_id: int):
        """會話斷開"""
        if cleaner_id in self.sessions:
            # 標記為離線
            self.sessions[cleaner_id].is_online = False
            
            # 更新 Redis
            r = await get_redis()
            if r:
                await r.hset(
                    self.CLEANER_SESSION_KEY.format(cleaner_id=cleaner_id),
                    "is_online",
                    "0"
                )
    
    async def queue_message(self, cleaner_id: int, message: dict):
        """將消息放入離線隊列"""
        r = await get_redis()
        if not r:
            return
        
        # 生成消息 ID
        msg_id = f"msg_{int(time.time() * 1000)}"
        message["msg_id"] = msg_id
        
        # 添加到隊列 (左側)
        await r.lpush(
            self.CLEANER_QUEUE_KEY.format(cleaner_id=cleaner_id),
            json.dumps(message)
        )
        
        # 設置過期時間
        await r.expire(
            self.CLEANER_QUEUE_KEY.format(cleaner_id=cleaner_id),
            self.QUEUE_TTL
        )
        
        # 限制隊列長度 (最多 50 條)
        await r.ltrim(
            self.CLEANER_QUEUE_KEY.format(cleaner_id=cleaner_id),
            0,
            49
        )
    
    async def replay_missed_messages(self, cleaner_id: int, last_event_id: str):
        """補發漏掉的消息"""
        r = await get_redis()
        if not r:
            return
        
        # 獲取離線期間的消息
        messages = await r.lrange(
            self.CLEANER_QUEUE_KEY.format(cleaner_id=cleaner_id),
            0,
            -1
        )
        
        if messages:
            # 找到最後收到的事件位置
            start_idx = 0
            for i, msg in enumerate(messages):
                try:
                    msg_data = json.loads(msg)
                    if msg_data.get("msg_id") == last_event_id:
                        start_idx = i + 1
                        break
                except:
                    pass
            
            # 補發後續消息
            missed = messages[start_idx:]
            
            # 存儲到待發送列表
            if missed:
                key = f"ws:pending:{cleaner_id}"
                for msg in missed:
                    await r.rpush(key, msg)
                await r.expire(key, 60)  # 1分鐘內必須領取
    
    async def get_pending_messages(self, cleaner_id: int) -> List[dict]:
        """獲取待補發的消息"""
        r = await get_redis()
        if not r:
            return []
        
        key = f"ws:pending:{cleaner_id}"
        messages = await r.lrange(key, 0, -1)
        
        # 刪除已獲取的消息
        await r.delete(key)
        
        result = []
        for msg in messages:
            try:
                result.append(json.loads(msg))
            except:
                pass
        
        return result
    
    async def is_online(self, cleaner_id: int) -> bool:
        """檢查清潔員是否在線"""
        # 先檢查內存
        if cleaner_id in self.sessions:
            return self.sessions[cleaner_id].is_online
        
        # 檢查 Redis
        r = await get_redis()
        if r:
            is_online = await r.hget(
                self.CLEANER_SESSION_KEY.format(cleaner_id=cleaner_id),
                "is_online"
            )
            return is_online == "1"
        
        return False


# 全局實例
mobile_ft = MobileFaultTolerance()
