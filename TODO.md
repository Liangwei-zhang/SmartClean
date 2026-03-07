# SmartClean 代辦事項

---

## ✅ 已完成

### 核心優化
- [x] FastAPI + Granian (Rust ASGI)
- [x] PostgreSQL 15 + PostGIS 3.4
- [x] Redis 兩級緩存 (L1+L2)
- [x] 悲觀鎖搶單 (SELECT FOR UPDATE SKIP LOCKED)
- [x] Redis Lua 原子搶單
- [x] Redis Pub/Sub 跨 Worker 廣播
- [x] Redis GEO 毫秒級地理查詢
- [x] PostGIS GIST 空間索引
- [x] Arq 異步任務隊列
- [x] S3/OSS 對象存儲
- [x] 移動端容錯 (心跳+消息補發)
- [x] 定向派單 (cleaner_id 精準推送)
- [x] 訂單距離計算 (API 返回)
- [x] 前端頁面加載優化
- [x] Rate Limiting (登入 10次/分, API 60次/分)
- [x] 監控系統 (/api/monitoring/stats)
- [x] 訂單狀態更新 Bug 修復
- [x] 統計分析儀表板 (/stats)

### 數據庫遷移 ✅
- [x] PostGIS 空間索引
- [x] 房源/房東關聯修復

---

## 🟠 P1 - 功能

- [ ] 通知系統 (短信/推送)
- [ ] 支付集成 (Stripe/LinePay)
- [ ] 評價系統

---

## 🟡 P2 - 長期

- [ ] 訂單分表 (按月)
- [ ] 讀寫分離
- [ ] 移動端 PWA 適配
- [ ] 客服系統集成
- [ ] 自動化測試 CI/CD
- [ ] OpenTelemetry 監控

---

## 📋 快速命令

```bash
# 啟動
cd /home/nico/projects/SmartClean
sudo ./run_optimized.sh

# Docker 部署
docker-compose -f docker-compose.prod.yml up -d
```
