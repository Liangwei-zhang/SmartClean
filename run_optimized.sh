#!/bin/bash
# SmartClean 啟動腳本 - 核彈優化版

export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2
export MALLOC_CONF="background_thread:true,metadata_thp:auto"

cd /home/nico/projects/SmartClean

# 使用 Granian (Rust 驅動，比 Uvicorn 快 30-150%)
# --threads: 啟用執行緒模式，更好利用多核 CPU
sudo PYTHONPATH=/home/nico/.local/lib/python3.12/site-packages:/home/nico/projects/SmartClean \
/usr/local/bin/granian --interface asgi \
    app.main:app \
    --host 0.0.0.0 --port 80 \
    --workers 4 \
    --threads 4
