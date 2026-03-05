#!/bin/bash
# SmartClean 啟動腳本 - 核彈優化版

export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2
export MALLOC_CONF="background_thread:true,metadata_thp:auto"

cd /home/nico/projects/SmartClean

# 使用 Granian (Rust 驅動)
exec granian --interface asgi \
    app.main:app \
    --host 0.0.0.0 --port 80 \
    --workers $(nproc) \
    --runtime-threads 4 \
    --backlog 2048 \
    --http auto \
    --log-level warning
