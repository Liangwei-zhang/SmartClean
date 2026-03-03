#!/bin/bash
# SmartClean 啟動腳本 - Granian + Uvicorn

echo "🚀 啟動 SmartClean (Granian Engine)..."

# 使用 Granian 運行 (Rust 驅動的 ASGI 伺服器)
# granian --interface ASGI3 --host 0.0.0.0 --port 80 app.main:app

# 或者使用 uvicorn (開發模式)
uvicorn app.main:app --host 0.0.0.0 --port 80 --reload
