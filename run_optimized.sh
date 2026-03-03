#!/bin/bash
# SmartClean 啟動腳本 - 優化版

export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2
export MALLOC_CONF="background_thread:true,metadata_thp:auto"

cd /home/nico/projects/SmartClean
sudo PYTHONPATH=/home/nico/.local/lib/python3.12/site-packages:/home/nico/projects/SmartClean \
/home/nico/.local/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
