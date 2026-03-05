# SmartClean Dockerfile
# 生產環境構建

FROM python:3.12-slim

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Rust (Granian 需要)
RUN pip install --no-cache-dir granian

# 設置工作目錄
WORKDIR /app

# 複製依賴文件
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用代碼
COPY app/ ./app/
COPY static/ ./static/
COPY uploads/ ./uploads/

# 創建非 root 用戶
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 80

# 啟動命令 - 使用 Granian (Rust 驅動)
CMD ["granian", "--interface", "asgi", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "4"]
