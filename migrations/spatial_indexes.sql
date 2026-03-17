-- SmartClean PostGIS 空間索引遷移
-- 執行方式: psql -U nico -d smartclean -f spatial_indexes.sql

-- 1. 啟用 PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Property 空間索引 (房源)
-- 方式 A: 使用 geography 類型 + GIST 索引 (推薦)
ALTER TABLE properties 
ADD COLUMN IF NOT EXISTS location geography(Point, 4326);

-- 更新 location 列
UPDATE properties 
SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography 
WHERE longitude IS NOT NULL AND latitude IS NOT NULL;

-- 建立 GIST 索引
CREATE INDEX IF NOT EXISTS idx_property_location_gist 
ON properties USING GIST (location);

-- 3. Cleaner 空間索引 (清潔員)
ALTER TABLE cleaners 
ADD COLUMN IF NOT EXISTS location geography(Point, 4326);

UPDATE cleaners 
SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography 
WHERE longitude IS NOT NULL AND latitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cleaner_location_gist 
ON cleaners USING GIST (location);

-- 4. 複合索引優化
CREATE INDEX IF NOT EXISTS idx_order_status_created 
ON orders (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cleaner_status 
ON cleaners (status);

-- 5. 驗證
-- SELECT indexname, indexdef FROM pg_indexes 
-- WHERE tablename IN ('properties', 'cleaners');

-- 6. 空間查詢示例
-- 查找附近 5km 內的清潔員:
/*
SELECT 
    id, name, phone, 
    ST_Distance(location, ST_SetSRID(ST_MakePoint(-114.0719, 51.0447), 4326)) as distance_m
FROM cleaners
WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(-114.0719, 51.0447), 4326), 5000)
AND status = 'online'
ORDER BY distance_m
LIMIT 10;
*/
-- PostGIS GIST 索引優化 (buffering)
-- 在大量更新坐標時開啟緩衝區
ALTER INDEX idx_property_location_gist SET (fillfactor = 80);
ALTER INDEX idx_cleaner_location_gist SET (fillfactor = 80);

-- 定期維護 (vacuum analyze)
VACUUM ANALYZE properties;
VACUUM ANALYZE cleaners;
