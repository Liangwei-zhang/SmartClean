# SmartClean 部署腳本
# 需要 PostgreSQL + Redis

# 1. 創建數據庫
# psql -U postgres -c "CREATE DATABASE smartclean;"

# 2. 安裝依賴
# pip install -r requirements.txt

# 3. 設置環境變量
# export DATABASE_URL="postgresql://user:pass@localhost:5432/smartclean"
# export REDIS_URL="redis://localhost:6379/0"
# export SECRET_KEY="your-secret-key"

# 4. 啟動 API
# uvicorn app.main:app --host 0.0.0.0 --port 80 --reload
