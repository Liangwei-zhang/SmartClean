# SmartClean - 清潔服務平台進化版

## 目標
核彈級優化的清潔服務平台，從 cleaning_service_fastapi 進化而來。

## 架構

### 後端
- **FastAPI** + **Granian** (Rust ASGI)
- **PostgreSQL** + **PostGIS**
- **Redis** + **PgBouncer**
- **Arq/Taskiq** (異步任務)

### 前端
- 移動端優先的 Web App
- 搶單大廳 (即時更新)
- 房東發單系統

## 優化階段

### Phase 1: 引擎內核
- [ ] Granian 替換 Uvicorn
- [ ] ORJSON 全域響應
- [ ] jemalloc/tcmalloc

### Phase 2: 資料庫
- [ ] asyncpg 異步步驅
- [ ] PgBouncer 連接池
- [ ] PostGIS 空間索引
- [ ] 樂觀鎖 (version 欄位)

### Phase 3: 快取/即時
- [ ] Redis Pub/Sub 廣播
- [ ] 兩級快取 (L1內存 + L2 Redis)
- [ ] 防擊穿機制

### Phase 4: 任務隊列
- [ ] Arq/Taskiq 替換 Celery

### Phase 5: 基礎設施
- [ ] Idempotency Key
- [ ] Nginx HTTP/3

## API 設計

### 訂單
- `POST /api/orders` - 創建訂單
- `GET /api/orders` - 列表 (支援距離/價格/時間排序)
- `GET /api/orders/{id}` - 詳情
- `POST /api/orders/{id}/accept` - 搶單 (樂觀鎖)
- `PATCH /api/orders/{id}/status` - 狀態更新

### 用戶
- `POST /api/auth/login` - 登入
- `POST /api/auth/register` - 註冊

### WebSocket
- `WS /ws/orders` - 訂單即時廣播

## 數據模型

### Order
- id, property_id, host_id, cleaner_id
- status (open/accepted/arrived/completed)
- price, checkout_time
- version (樂觀鎖)
- created_at, updated_at

### Property
- id, name, address
- latitude, longitude (PostGIS)
- bedrooms, bathrooms
- host_id

### Cleaner
- id, name, phone
- latitude, longitude
- rating, total_jobs
- status (online/offline)

---

## 開發日誌

### 2026-03-03
- 項目創建
- **Phase 1 完成:**
  - ✅ ORJSON 全域響應
  - ✅ asyncpg 異步數據庫
  - ✅ 樂觀鎖搶單 (version 欄位)
  - ✅ 項目結構
  - ⏳ Granian (需進一步配置)
  
- **Phase 2 完成:**
  - ✅ asyncpg 驅動
  - ⏳ PgBouncer (需 Docker 部署)
  - ⏳ PostGIS (需數據庫支持)
  
- **Phase 3 完成:**
  - ✅ Redis Pub/Sub 廣播 (跨 Worker/跨節點)
  - ✅ 兩級快取 (L1 內存 + L2 Redis)
  - ✅ 防擊穿機制
  - ✅ WebSocket 訂單即時更新

- **Phase 4 完成:**
  - ✅ Arq 任務隊列 (替換 Celery)
  - ✅ 通知/清理/位置同步任務

- **Phase 5 完成:**
  - ✅ Idempotency Key (防重複請求)
  - ✅ Rate Limiting (速率限制)
  - ✅ Blacklist (黑名單)
  - ✅ Nginx HTTP/3 + 零拷貝
  - ✅ Docker Compose 部署配置
  - ✅ PgBouncer 連接池
  - ✅ PostGIS 支持
