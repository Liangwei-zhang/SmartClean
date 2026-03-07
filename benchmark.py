"""
壓測腳本 - SmartClean API
使用 locust 進行負載測試
"""
import os
import sys
from locust import HttpUser, task, between, events
import random
import json

# 訂單測試數據
ORDER_DATA = {
    "property_id": 10,
    "price": round(random.uniform(100, 500), 2),
    "checkout_time": "2026-03-10T14:00:00",
    "text_notes": "壓測訂單"
}

CLEANER_IDS = list(range(20, 30))
PROPERTY_IDS = list(range(1, 12))


class SmartCleanUser(HttpUser):
    """SmartClean 模擬用戶"""
    
    wait_time = between(0.1, 0.5)  # 請求間隔
    
    def on_start(self):
        """初始化"""
        self.cleaner_id = random.choice(CLEANER_IDS)
        self.property_id = random.choice(PROPERTY_IDS)
    
    @task(10)
    def get_orders(self):
        """獲取訂單列表 (最頻繁)"""
        self.client.get("/api/orders?limit=20")
    
    @task(5)
    def get_open_orders(self):
        """獲取開放訂單"""
        self.client.get("/api/orders?status=open")
    
    @task(3)
    def get_stats(self):
        """獲取統計"""
        self.client.get("/api/stats")
    
    @task(2)
    def get_dashboard(self):
        """獲取儀表板"""
        self.client.get("/api/stats/dashboard")
    
    @task(2)
    def get_cleaners(self):
        """獲取清潔員列表"""
        self.client.get("/api/cleaners")
    
    @task(1)
    def get_properties(self):
        """獲取房源列表"""
        self.client.get("/api/properties")
    
    @task(1)
    def accept_order(self):
        """搶單 (低權重)"""
        # 先獲取一個開放訂單
        response = self.client.get("/api/orders?status=open&limit=1")
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                order_id = data["data"][0]["id"]
                self.client.post(
                    f"/api/orders/{order_id}/accept",
                    json={
                        "cleaner_id": self.cleaner_id,
                        "cleaner_name": f"清潔員{self.cleaner_id}"
                    }
                )
    
    @task(1)
    def health_check(self):
        """健康檢查"""
        self.client.get("/health")


class HighConcurrencyUser(HttpUser):
    """高併發用戶 - 專門測試搶單"""
    
    wait_time = between(0.01, 0.1)  # 極短間隔
    
    @task
    def grab_order(self):
        """搶單測試"""
        # 獲取開放訂單
        response = self.client.get("/api/orders?status=open&limit=5")
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                # 隨機選一個訂單
                order = random.choice(data["data"])
                order_id = order["id"]
                
                # 嘗試搶單
                self.client.post(
                    f"/api/orders/{order_id}/accept",
                    json={
                        "cleaner_id": random.choice(CLEANER_IDS),
                        "cleaner_name": f"測試{self.cleaner_id}"
                    },
                    catch_response=True
                )


# === 測試報告 ===
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("🚀 壓測開始!")
    print(f"   主機: {environment.host}")
    print(f"   用戶數: {environment.runner.user_count if hasattr(environment.runner, 'user_count') else 'N/A'}")


@events.test_stop.add_listener  
def on_test_stop(environment, **kwargs):
    print("\n📊 壓測結束!")
    print("   查看詳細報告: locust -f benchmark.py --report-html report.html")


# 快速測試 (不啟動 Web UI)
if __name__ == "__main__":
    os.system("locust -f benchmark.py --headless -u 100 -r 10 -t 60s --host http://localhost")
