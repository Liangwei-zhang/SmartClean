"""
地理查詢 API - 附近清潔員 / 附近訂單
"""
from fastapi import APIRouter, Query
from typing import Optional

from app.core.geo import geo_service
from app.core.response import success_response

router = APIRouter()


@router.get("/nearby/cleaners")
async def get_nearby_cleaners(
    lat: float = Query(..., description="緯度"),
    lon: float = Query(..., description="經度"),
    radius_km: float = Query(5, description="搜索半徑 (公里)"),
    limit: int = Query(10, description="返回數量")
):
    """
    查找附近清潔員 (Redis GEO, 毫秒級)
    
    使用 Redis GEOSEARCH 進行高速空間查詢
    """
    cleaners = await geo_service.get_nearby_cleaners(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=limit
    )
    
    return success_response(data={
        "cleaners": cleaners,
        "count": len(cleaners),
        "search_radius_km": radius_km
    })


@router.get("/nearby/orders")
async def get_nearby_orders(
    lat: float = Query(..., description="緯度"),
    lon: float = Query(..., description="經度"),
    radius_km: float = Query(10, description="搜索半徑 (公里)"),
    status: str = Query("open", description="訂單狀態過濾"),
    limit: int = Query(20, description="返回數量")
):
    """
    查找附近訂單 (Redis GEO, 毫秒級)
    """
    orders = await geo_service.get_nearby_orders(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        status=status,
        limit=limit
    )
    
    return success_response(data={
        "orders": orders,
        "count": len(orders),
        "search_radius_km": radius_km
    })


@router.post("/cleaner/location")
async def update_cleaner_location(
    cleaner_id: int,
    lat: float,
    lon: float
):
    """
    更新清潔員位置 (每次 GPS 定位上報時調用)
    """
    success = await geo_service.update_cleaner_location(cleaner_id, lat, lon)
    
    if success:
        return success_response(message="位置已更新")
    else:
        return success_response(success=False, message="位置更新失敗")
