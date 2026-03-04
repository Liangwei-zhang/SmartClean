"""
Geocode API - 地址驗證
"""
from fastapi import APIRouter, Query
import httpx

router = APIRouter()


@router.get("/geocode")
async def geocode(address: str = Query(...)):
    """地址驗證"""
    try:
        async with httpx.AsyncClient() as client:
            # 使用 Nominatim API
            url = f"https://nominatim.openstreetmap.org/search"
            params = {
                "format": "json",
                "addressdetails": 1,
                "q": address,
                "limit": 1
            }
            headers = {"User-Agent": "SmartClean/1.0"}
            
            resp = await client.get(url, params=params, headers=headers, timeout=10.0)
            data = resp.json()
            
            if data and len(data) > 0:
                result = data[0]
                addr = result.get("address", {})
                
                return {
                    "success": True,
                    "province": addr.get("province", ""),
                    "city": addr.get("city") or addr.get("town") or addr.get("village", ""),
                    "street": addr.get("road", ""),
                    "house_number": addr.get("house_number", ""),
                    "postcode": addr.get("postcode", ""),
                    "lat": result.get("lat"),
                    "lon": result.get("lon"),
                }
            else:
                return {"success": False, "error": "地址無法識別"}
    except Exception as e:
        return {"success": False, "error": str(e)}
