# SmartClean 代辦事項

---

## ✅ 已完成 (核彈優化)

### 第一階段：引擎內核
- [x] ORJSON 響應加速
- [x] Granian (Rust ASGI) ← 剛配置
- [x] Jemalloc 記憶體優化

### 第二階段：資料庫
- [x] Asyncpg 異步驅動
- [x] PgBouncer 連接池
- [x] 樂觀鎖 (version)
- [x] PostGIS 空間索引 (GIST) ✅ 2026-03-06
- [x] Redis GEO 毫秒級查詢 ✅ 2026-03-06

### 第三階段：快取通訊
- [x] 兩級快取 (L1+L2)
- [x] 防擊穿機制
- [x] Redis Pub/Sub WebSocket

### 第四階段：任務隊列
- [x] Arq 替換 Celery

### 第五階段：基礎設施
- [x] Idempotency Key
- [x] Nginx HTTP/3 + 零拷貝
- [x] Rate Limiting

---

## 🔴 P0 - 立即執行

### 1. 啟動服務測試 Granian
```bash
cd /home/nico/projects/SmartClean
sudo ./run_optimized.sh
```

### 2. 驗證 PostGIS 是否啟用
```sql
SELECT postgis_version();
```

### 3. 數據庫遷移 (如有需要)
```bash
alembic upgrade head
```

---

## 🟠 P1 - 本週任務

### 功能擴展
- [ ] 通知系統 (Arq tasks)
- [ ] 支付集成 Stripe/LinePay
- [ ] 評價系統
- [ ] 統計分析儀表板

### 性能測試
- [ ] 使用 wrk/locust 壓測 RPS
- [ ] WebSocket 延遲測試
- [ ] 數據庫併發測試

---

## 🟡 P2 - 下月規劃

- [ ] 移動端 PWA 適配
- [ ] 客服系統集成
- [ ] 自動化測試 CI/CD
- [ ] 監控報警 (Sentry + Prometheus)

---

## 📋 快速命令

```bash
# 啟動 (使用 Granian)
cd /home/nico/projects/SmartClean
sudo ./run_optimized.sh

# Docker 部署
docker-compose -f docker-compose.prod.yml up -d

# 數據庫遷移
alembic upgrade head
```
