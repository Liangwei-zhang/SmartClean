"""
Geocode API — 地址驗證
公開讀取（前端地址驗證用），但做速率限制防止濫用
"""
import logging
from fastapi import APIRouter, Query
import httpx
from app.core.cache import get_from_cache, set_cache, cache_key

logger = logging.getLogger(__name__)
router = APIRouter()  # public endpoint — auth via middleware rate-limit


@router.get("/geocode")
async def geocode(address: str = Query(..., max_length=500)):
    """地址驗證 + 座標查詢（含緩存，公開但限速由 middleware 處理）"""
    if not address.strip():
        return {"success": False, "error": "地址不可為空"}

    ck     = cache_key("geocode", address=address)
    cached = await get_from_cache(ck)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"format": "json", "addressdetails": 1, "q": address, "limit": 1},
                headers={"User-Agent": "SmartClean/3.0"},
            )
            data = resp.json()

        if data:
            addr = data[0].get("address", {})
            result = {
                "success":      True,
                "province":     addr.get("state") or addr.get("province", ""),
                "city":         addr.get("city") or addr.get("town") or addr.get("village", ""),
                "street":       addr.get("road", ""),
                "house_number": addr.get("house_number", ""),
                "postcode":     addr.get("postcode", ""),
                "lat":          data[0].get("lat"),
                "lon":          data[0].get("lon"),
            }
            await set_cache(ck, result, ttl_l1=3600, ttl_l2=86400)
            return result
        return {"success": False, "error": "地址無法識別"}
    except Exception as exc:
        logger.warning("Geocode error: %s", exc)
        return {"success": False, "error": "地址驗證服務暫時不可用"}
