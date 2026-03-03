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

---

## ✅ 已完成 (All Phases)

### Phase 1: 引擎內核 ✅
- ✅ ORJSON 全域響應
- ✅ asyncpg 異步步驅
- ⏳ Granian (需進一步配置)
- ⏳ jemalloc/tcmalloc

### Phase 2: 資料庫 ✅
- ✅ 樂觀鎖 (version 欄位)
- ⏳ PgBouncer (需 Docker 部署)
- ⏳ PostGIS (需數據庫支持)

### Phase 3: 快取/即時 ✅
- ✅ Redis Pub/Sub 廣播
- ✅ 兩級快取 + 防擊穿
- ✅ WebSocket

### Phase 4: 任務隊列 ✅
- ✅ Arq

### Phase 5: 基礎設施 ✅
- ✅ Idempotency Key
- ✅ Rate Limiting
- ✅ Nginx HTTP/3
- ✅ Docker Compose

---

## 🔲 待辦 (TODO)

### 後端
- [ ] 房源管理 API (Property CRUD)
- [ ] 清潔工位置更新 API
- [ ] 訂單狀態更新 API (arrived/completed)
- [ ] 圖片上傳 API

### 前端
- [ ] 搶單大廳頁面 (cleaner.html)
- [ ] 房東發單頁面 (host.html)
- [ ] 管理員頁面 (admin.html)

### 部署
- [ ] 測試環境部署
- [ ] PostgreSQL + Redis 初始化
- [ ] 生產環境部署

---

## 開發日誌

### 2026-03-03
- 項目創建並推送至 GitHub
- 所有 5 個 Phase 代碼完成
