"""
PostGIS 空間索引遷移腳本
"""
# 此遷移需要手動執行，或通過 Alembic 運行

MIGRATION_SQL = """
-- 1. 確保 PostGIS 已啟用
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. 將 lat/lng 轉換為 GEOGRAPHY 類型 (如果需要)
-- 注意：這是可選的，float 字段 + GIST 索引也能工作

-- 3. 為 Property 建立 GIST 空間索引
CREATE INDEX IF NOT EXISTS idx_property_geo_gist 
ON properties 
USING GIST (geography(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)));

-- 4. 為 Cleaner 建立 GIST 空間索引
CREATE INDEX IF NOT EXISTS idx_cleaner_geo_gist 
ON cleaners 
USING GIST (geography(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)));

-- 5. 為 Order 建立複合索引 (狀態 + 創建時間)
CREATE INDEX IF NOT EXISTS idx_order_status_created 
ON orders (status, created_at DESC);

-- 6. 驗證索引
-- SELECT * FROM pg_indexes WHERE tablename IN ('properties', 'cleaners');
"""

# 空間查詢示例 SQL
SPATIAL_QUERIES = {
    # 查找附近 10km 內的房源
    "nearby_properties": """
        SELECT 
            id, name, address,
            ST_Distance(
                geography(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)),
                geography(ST_SetSRIN(ST_MakePoint(:lon, :lat), 4326))
            ) as distance_meters
        FROM properties
        WHERE ST_DWithin(
            geography(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)),
            geography(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)),
            :radius_meters
        )
        ORDER BY distance_meters
        LIMIT :limit;
    """,
    
    # 查找附近 5km 內的清潔工
    "nearby_cleaners": """
        SELECT 
            id, name, phone, rating, status,
            ST_Distance(
                geography(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)),
                geography(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            ) as distance_meters
        FROM cleaners
        WHERE ST_DWithin(
            geography(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)),
            geography(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)),
            :radius_meters
        )
        AND status = 'online'
        ORDER BY distance_meters
        LIMIT :limit;
    """
}
