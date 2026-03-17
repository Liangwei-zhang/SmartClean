import logging
logger = logging.getLogger(__name__)
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "SmartClean"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/smartclean")
    DATABASE_URL_SYNC: str = os.getenv("DATABASE_URL_SYNC", "postgresql://postgres:postgres@localhost:5432/smartclean")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # JWT - 必須從環境變量讀取
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    if not SECRET_KEY:
        import secrets as _secrets_module
        SECRET_KEY = _secrets_module.token_hex(32)
        logger.warning("%s", "⚠️ WARNING: Using auto-generated SECRET_KEY. Set SECRET_KEY env var for production!")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days default
    
    # CORS - 限制域名
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "")  # 逗號分隔的域名列表
    
    # Upload
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", str(10 * 1024 * 1024)))  # 10MB
    
    # Custom
    X_BEARER_TOKEN: str = os.getenv("X_BEARER_TOKEN", "")
    NICO_TELEGRAM_ID: str = ""
    
    # S3 / Object Storage
    S3_ENABLED: bool = False
    S3_ENDPOINT_URL: str = ""  # e.g., https://s3.amazonaws.com or https://oss-cn-hangzhou.aliyuncs.com
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = "smartclean"
    S3_REGION: str = "us-east-1"
    S3_PUBLIC_URL: str = ""  # CDN URL if available
    
    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
