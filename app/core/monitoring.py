"""
日誌與監控系統
"""
import time
import logging
import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict
import asyncio
import threading

# 配置日誌
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("smartclean")

# 內存指標存儲
class Metrics:
    """簡單的內存指標收集器"""
    _lock = threading.Lock()
    _data = {
        "requests": defaultdict(int),      # 各端點請求次數
        "errors": defaultdict(int),        # 各端點錯誤次數
        "durations": defaultdict(list),   # 各端點響應時間
        "ws_connections": 0,               # WebSocket 連接數
        "ws_messages": 0,                  # WebSocket 消息數
    }
    
    @classmethod
    def record_request(cls, endpoint: str, duration: float, status: int):
        with cls._lock:
            cls._data["requests"][endpoint] += 1
            if status >= 400:
                cls._data["errors"][endpoint] += 1
            cls._data["durations"][endpoint].append(duration)
            # 只保留最近1000條
            if len(cls._data["durations"][endpoint]) > 1000:
                cls._data["durations"][endpoint] = cls._data["durations"][endpoint][-1000:]
    
    @classmethod
    def record_ws_connect(cls):
        with cls._lock:
            cls._data["ws_connections"] += 1
    
    @classmethod
    def record_ws_message(cls):
        with cls._lock:
            cls._data["ws_messages"] += 1
    
    @classmethod
    def get_stats(cls) -> dict:
        with cls._lock:
            stats = {}
            for endpoint, count in cls._data["requests"].items():
                durations = cls._data["durations"].get(endpoint, [])
                errors = cls._data["errors"].get(endpoint, 0)
                
                avg_duration = sum(durations) / len(durations) if durations else 0
                p95_duration = sorted(durations)[int(len(durations) * 0.95)] if durations else 0
                
                stats[endpoint] = {
                    "requests": count,
                    "errors": errors,
                    "error_rate": round(errors / count * 100, 2) if count > 0 else 0,
                    "avg_duration_ms": round(avg_duration * 1000, 2),
                    "p95_duration_ms": round(p95_duration * 1000, 2),
                }
            
            return {
                "endpoints": stats,
                "websocket": {
                    "total_connections": cls._data["ws_connections"],
                    "total_messages": cls._data["ws_messages"],
                },
                "timestamp": datetime.now().isoformat()
            }
    
    @classmethod
    def reset(cls):
        with cls._lock:
            cls._data = {
                "requests": defaultdict(int),
                "errors": defaultdict(int),
                "durations": defaultdict(list),
                "ws_connections": 0,
                "ws_messages": 0,
            }


def log_request(endpoint: str, duration: float, status: int, method: str = "GET"):
    """記錄請求日誌"""
    # 記錄到 Metrics
    Metrics.record_request(endpoint, duration, status)
    
    # 結構化日誌
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "method": method,
        "endpoint": endpoint,
        "duration_ms": round(duration * 1000, 2),
        "status": status,
    }
    
    if status >= 500:
        logger.error(f"Server Error: {json.dumps(log_data)}")
    elif status >= 400:
        logger.warning(f"Client Error: {json.dumps(log_data)}")
    else:
        logger.info(f"{method} {endpoint} - {status} - {duration*1000:.1f}ms")


def log_event(event_type: str, data: dict = None):
    """記錄業務事件"""
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        "data": data or {}
    }
    logger.info(f"Event: {json.dumps(log_data)}")
