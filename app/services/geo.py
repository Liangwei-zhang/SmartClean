"""
空間查詢 - PostGIS 實現
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def find_nearby_orders(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_km: float = 10,
    limit: int = 20
):
    """
    查找附近訂單 - 使用 PostGIS ST_DWithin
    比計算機距離公式快得多
    """
    query = text("""
        SELECT o.*, 
               ST_Distance(
                   ST_SetSRID(ST_MakePoint(p.longitude, p.latitude), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
               ) / 1000 as distance_km
        FROM orders o
        JOIN properties p ON o.property_id = p.id
        WHERE o.status = 'OPEN'
          AND ST_DWithin(
              ST_SetSRID(ST_MakePoint(p.longitude, p.latitude), 4326)::geography,
              ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
              :radius * 1000
          )
        ORDER BY distance_km
        LIMIT :limit
    """)
    
    result = await db.execute(query, {
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
        "limit": limit
    })
    
    return result.fetchall()


async def find_nearby_cleaners(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_km: float = 10,
    limit: int = 20
):
    """
    查找附近清潔工 - 使用 PostGIS
    """
    query = text("""
        SELECT c.*,
               ST_Distance(
                   ST_SetSRID(ST_MakePoint(c.longitude, c.latitude), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
               ) / 1000 as distance_km
        FROM cleaners c
        WHERE c.status = 'online'
          AND ST_DWithin(
              ST_SetSRID(ST_MakePoint(c.longitude, c.latitude), 4326)::geography,
              ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
              :radius * 1000
          )
        ORDER BY distance_km
        LIMIT :limit
    """)
    
    result = await db.execute(query, {
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
        "limit": limit
    })
    
    return result.fetchall()
