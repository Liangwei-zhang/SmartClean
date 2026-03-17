"""
S3 / Object Storage Service
支持 AWS S3, MinIO, Aliyun OSS 等兼容 S3 的存儲
"""
import asyncio
import uuid
import hashlib
from pathlib import Path
from typing import Optional
import aiofiles
from datetime import datetime, timedelta

from app.core.config import get_settings

settings = get_settings()

# Lazy import boto3
_s3_client = None


async def get_s3_client():
    """延遲加載 S3 客戶端"""
    global _s3_client
    if _s3_client is None:
        try:
            import aiobotocore.session
            from aiobotocore.config import AioConfig
            
            # 配置連接
            config = AioConfig(
                connect_timeout=5,
                read_timeout=10,
                retries={'max_attempts': 3}
            )
            
            session = aiobotocore.session.get_session()
            _s3_client = session.create_client(
                's3',
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION,
                config=config
            )
        except ImportError:
            return None
    return _s3_client


async def upload_to_s3(
    file_bytes: bytes,
    key: str,
    content_type: str = "image/jpeg"
) -> str:
    """
    上傳文件到 S3
    
    Returns:
        URL of the uploaded file
    """
    if not settings.S3_ENABLED:
        raise RuntimeError("S3 is not enabled")
    
    client = await get_s3_client()
    if not client:
        raise RuntimeError("S3 client not available")
    
    # 上傳
    await client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
        # 設置緩存頭
        CacheControl='public, max-age=86400',
    )
    
    # 返回 URL
    if settings.S3_PUBLIC_URL:
        return f"{settings.S3_PUBLIC_URL}/{key}"
    else:
        # 生成預簽名 URL (24小時有效期)
        # 注意: 這裡需要同步客戶端，暫時返回 bucket URL
        return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com/{key}"


async def delete_from_s3(key: str) -> bool:
    """從 S3 刪除文件"""
    if not settings.S3_ENABLED:
        return False
    
    client = await get_s3_client()
    if not client:
        return False
    
    try:
        await client.delete_object(
            Bucket=settings.S3_BUCKET,
            Key=key
        )
        return True
    except:
        return False


async def generate_presigned_url(key: str, expires_seconds: int = 3600) -> str:
    """生成預簽名 URL (用於私有 bucket)"""
    if not settings.S3_ENABLED:
        raise RuntimeError("S3 is not enabled")
    
    client = await get_s3_client()
    if not client:
        raise RuntimeError("S3 client not available")
    
    try:
        # aiobotocore 不直接支持 presigned URL，改用同步方式
        import boto3
        s3 = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION
        )
        
        url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.S3_BUCKET,
                'Key': key
            },
            ExpiresIn=expires_seconds
        )
        return url
    except Exception as e:
        # 回退到 public URL
        if settings.S3_PUBLIC_URL:
            return f"{settings.S3_PUBLIC_URL}/{key}"
        raise


def generate_s3_key(filename: str, folder: str = "images") -> str:
    """生成 S3 key"""
    # 使用日期分層 + UUID 避免衝突
    now = datetime.now()
    date_path = now.strftime("%Y/%m/%d")
    uuid_part = uuid.uuid4().hex[:8]
    
    # 根據擴展名確定 content type
    ext = Path(filename).suffix.lower()
    if ext in ['.jpg', '.jpeg']:
        content_type = "image/jpeg"
    elif ext == '.png':
        content_type = "image/png"
    elif ext == '.webp':
        content_type = "image/webp"
    elif ext in ['.m4a', '.mp3', '.wav']:
        content_type = "audio/mpeg"
    else:
        content_type = "application/octet-stream"
    
    key = f"{folder}/{date_path}/{uuid_part}{ext}"
    return key, content_type
