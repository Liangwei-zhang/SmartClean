#!/usr/bin/env python3
"""
簡單壓測腳本
"""
import asyncio
import aiohttp
import time
import random
from concurrent.futures import ThreadPoolExecutor
import sys

URL = "http://localhost"
ENDPOINTS = [
    "/api/orders?limit=20",
    "/api/orders?status=open",
    "/api/stats",
    "/api/stats/dashboard",
    "/api/cleaners",
    "/api/properties",
]

TOTAL_REQUESTS = 500
CONCURRENT = 50

results = {
    "success": 0,
    "error": 0,
    "latencies": []
}

def make_request(session, endpoint):
    """發送請求"""
    try:
        start = time.time()
        resp = session.get(f"{URL}{endpoint}", timeout=10)
        latency = time.time() - start
        
        if resp.status_code == 200:
            results["success"] += 1
        else:
            results["error"] += 1
        
        results["latencies"].append(latency)
    except Exception as e:
        results["error"] += 1

async def run_test():
    """運行壓測"""
    print(f"🚀 開始壓測: {TOTAL_REQUESTS} 請求, {CONCURRENT} 並發")
    print(f"   URL: {URL}")
    print("-" * 50)
    
    start_time = time.time()
    
    # 使用線程池
    with ThreadPoolExecutor(max_workers=CONCURRENT) as executor:
        with requests.Session() as session:
            futures = []
            for _ in range(TOTAL_REQUESTS):
                endpoint = random.choice(ENDPOINTS)
                futures.append(executor.submit(make_request, session, endpoint))
            
            # 等待完成
            for f in futures:
                f.result()
    
    total_time = time.time() - start_time
    
    # 計算結果
    latencies = sorted(results["latencies"])
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
    rps = TOTAL_REQUESTS / total_time
    
    print("-" * 50)
    print("📊 壓測結果")
    print("-" * 50)
    print(f"   總請求數: {TOTAL_REQUESTS}")
    print(f"   成功: {results['success']}")
    print(f"   失敗: {results['error']}")
    print(f"   成功率: {results['success']/TOTAL_REQUESTS*100:.1f}%")
    print(f"   總耗時: {total_time:.2f}s")
    print(f"   RPS: {rps:.1f}")
    print("-" * 50)
    print(f"   平均延遲: {avg_latency*1000:.1f}ms")
    print(f"   P50: {p50*1000:.1f}ms")
    print(f"   P95: {p95*1000:.1f}ms")
    print(f"   P99: {p99*1000:.1f}ms")
    print("-" * 50)

if __name__ == "__main__":
    import requests
    run_test()
