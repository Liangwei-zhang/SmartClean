import logging
logger = logging.getLogger(__name__)
"""
Redis GEO 服務 - 毫秒級地理查詢
用於清潔員位置實時追蹤和附近訂單查找
"""
from typing import List, Tuple, Optional
import json
import time as time_module
from app.core.cache import get_redis, cache_key

# Redis Key 前綴
CLEANER_GEO_KEY = "geo:cleaners"
ORDER_GEO_KEY = "geo:orders"


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine 公式計算距離 (公里)"""
    import math
    R = 6371  # 地球半徑 (km)
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


class GeoService:
    """Redis GEO 服務"""
    
    @staticmethod
    async def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
        """計算兩點之間的距離 (公里)"""
        r = await get_redis()
        if not r:
            # 回退到 Haversine 公式
            return _haversine_distance(lat1, lon1, lat2, lon2)
        
        try:
            # 使用 Redis GEODIST
            distance = await r.geodist(
                CLEANER_GEO_KEY,
                f"{lon1},{lat1}",  # 注意: Redis GEO 使用 lon,lat 順序
                f"{lon2},{lat2}",
                unit="km"
            )
            if distance:
                return float(distance)
        except Exception as e:
            logger.warning("%s", "Redis geodist failed: {e}")
        
        return _haversine_distance(lat1, lon1, lat2, lon2)
    
    @staticmethod
    async def update_cleaner_location(cleaner_id: int, lat: float, lon: float) -> bool:
        """更新清潔員位置"""
        r = await get_redis()
        if not r:
            return False
        
        try:
            # 使用 GEOADD 存儲位置
            await r.geoadd(CLEANER_GEO_KEY, (lon, lat, str(cleaner_id)))
            
            # 同時更新 hash 表存儲額外信息
            await r.hset(
                f"cleaner:location:{cleaner_id}",
                mapping={
                    "lat": str(lat),
                    "lon": str(lon),
                    "updated_at": str(int(time_module.time() * 1000))
                }
            )
            return True
        except Exception as e:
            logger.warning("%s", "Failed to update cleaner location: {e}")
            return False
    
    @staticmethod
    async def get_nearby_cleaners(
        lat: float, 
        lon: float, 
        radius_km: float = 5,
        limit: int = 10
    ) -> List[dict]:
        """
        查找附近清潔員 (毫秒級)
        
        Args:
            lat: 緯度
            lon: 經度
            radius_km: 半徑 (公里)
            limit: 返回數量
        
        Returns:
            [{"id": 1, "name": "John", "distance_km": 1.2, "lat": ..., "lon": ...}, ...]
        """
        r = await get_redis()
        if not r:
            return []
        
        try:
            # 使用 GEOSEARCH (Redis 6.2+) 或 GEORADIUS
            results = await r.geosearch(
                CLEANER_GEO_KEY,
                member=(lon, lat),
                unit="km",
                radius=radius_km,
                withdist=True,
                withcoord=True,
                sort="ASC",
                count=limit
            )
            
            cleaners = []
            for item in results:
                cleaner_id = item[0]
                distance = round(item[1], 2)  # km
                coords = item[2]
                
                # 獲取詳細信息
                detail = await r.hgetall(f"cleaner:location:{cleaner_id}")
                
                cleaners.append({
                    "id": int(cleaner_id),
                    "distance_km": distance,
                    "lat": float(detail.get("lat", coords[1])) if detail else coords[1],
                    "lon": float(detail.get("lon", coords[0])) if detail else coords[0]
                })
            
            return cleaners
        except Exception as e:
            logger.warning("%s", "Failed to get nearby cleaners: {e}")
            return []
    
    @staticmethod
    async def get_nearby_orders(
        lat: float, 
        lon: float, 
        radius_km: float = 10,
        status: str = "open",
        limit: int = 20
    ) -> List[dict]:
        """
        查找附近訂單
        
        注意: 訂單位置是固定的 (來自 Property)，應該定期同步
        """
        r = await get_redis()
        if not r:
            return []
        
        try:
            results = await r.geosearch(
                ORDER_GEO_KEY,
                member=(lon, lat),
                unit="km",
                radius=radius_km,
                withdist=True,
                withcoord=True,
                sort="ASC",
                count=limit
            )
            
            orders = []
            for item in results:
                order_id = item[0]
                distance = round(item[1], 2)
                
                # 從 Redis 獲取訂單基本信息
                order_data = await r.hgetall(f"order:info:{order_id}")
                
                if order_data:
                    orders.append({
                        "id": int(order_id),
                        "distance_km": distance,
                        "price": float(order_data.get("price", 0)),
                        "property_name": order_data.get("property_name", "")
                    })
            
            return orders
        except Exception as e:
            logger.warning("%s", "Failed to get nearby orders: {e}")
            return []
    
    @staticmethod
    async def sync_order_location(order_id: int, lat: float, lon: float) -> bool:
        """同步訂單位置到 Redis (創建訂單時調用)"""
        r = await get_redis()
        if not r:
            return False
        
        try:
            await r.geoadd(ORDER_GEO_KEY, (lon, lat, str(order_id)))
            return True
        except:
            return False
    
    @staticmethod
    async def remove_cleaner(cleaner_id: int) -> bool:
        """移除清潔員位置"""
        r = await get_redis()
        if not r:
            return False
        
        try:
            await r.zrem(CLEANER_GEO_KEY, str(cleaner_id))
            await r.delete(f"cleaner:location:{cleaner_id}")
            return True
        except:
            return False


# 便捷函數
geo_service = GeoService()
