"""地理查詢 API"""
from fastapi import APIRouter, Query, Depends
from app.core.auth  import require_cleaner, TokenData
from app.core.geo   import geo_service
from app.core.response import success_response

router = APIRouter()

@router.get("/nearby/cleaners")
async def get_nearby_cleaners(lat: float=Query(...), lon: float=Query(...),
    radius_km: float=Query(5), limit: int=Query(10),
    _: TokenData = Depends(require_cleaner)):
    cleaners = await geo_service.get_nearby_cleaners(lat=lat, lon=lon, radius_km=radius_km, limit=limit)
    return success_response(data={"cleaners": cleaners, "count": len(cleaners), "search_radius_km": radius_km})

@router.get("/nearby/orders")
async def get_nearby_orders(lat: float=Query(...), lon: float=Query(...),
    radius_km: float=Query(10), status: str=Query("open"), limit: int=Query(20)):
    orders = await geo_service.get_nearby_orders(lat=lat, lon=lon, radius_km=radius_km, status=status, limit=limit)
    return success_response(data={"orders": orders, "count": len(orders), "search_radius_km": radius_km})

@router.post("/cleaner/location")
async def update_cleaner_location(cleaner_id: int, lat: float, lon: float,
    token: TokenData = Depends(require_cleaner)):
    from fastapi import HTTPException
    if token.user_id != cleaner_id:
        raise HTTPException(status_code=403, detail="只能更新自己的位置")
    ok = await geo_service.update_cleaner_location(cleaner_id, lat, lon)
    return success_response(message="位置已更新" if ok else "位置更新失敗")
