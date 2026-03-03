# SmartClean - 清潔服務平台進化版

## 目標
核彈級優化的清潔服務平台，從 cleaning_service_fastapi 進化而來。

---

## ✅ 已完成

### 後端 API
- [x] 訂單管理 (CRUD + 樂觀鎖搶單)
- [x] 房源管理 (Property CRUD)
- [x] 清潔工管理 (位置/狀態更新)
- [x] 認證 (JWT + bcrypt)
- [x] 圖片/語音上傳 (Pillow 壓縮)

### 前端
- [x] cleaner.html - 搶單大廳
- [x] host.html - 房東發單
- [x] admin.html - 管理後台

### 優化
- [x] ORJSON 響應
- [x] asyncpg 異步驅動
- [x] Redis Pub/Sub 廣播
- [x] 兩級快取 + 防擊穿
- [x] 樂觀鎖
- [x] Idempotency Key
- [x] Rate Limiting
- [x] Docker Compose 配置

### 部署
- [x] PostgreSQL 數據庫
- [x] Redis 緩存
- [x] API 運行中 (port 80)

---

## 🔲 待辦

### 可選優化
- [ ] Granian (Rust ASGI) - 需額外配置
- [ ] jemalloc/tcmalloc - 需系統級安裝
- [ ] PgBouncer - 需 Docker 部署
- [ ] PostGIS - 需數據庫 Extension

### 功能擴展
- [ ] 通知系統 (Arq tasks)
- [ ] 支付集成
- [ ] 評價系統
- [ ] 統計分析

---

## 當前狀態
- ✅ 運行中: http://localhost
- ✅ 數據庫: PostgreSQL smartclean
- ✅ 緩存: Redis
