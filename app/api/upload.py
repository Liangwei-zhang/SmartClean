"""
圖片上傳 API - 支持本地存儲和 S3
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import os
import uuid
from pathlib import Path
from PIL import Image
import io

from app.core.database import get_db
from app.core.response import success_response
from app.core.config import get_settings
from app.models.models import Order

# S3 上傳 (條件導入)
try:
    from app.core.s3 import upload_to_s3, generate_s3_key, settings as s3_settings
    S3_ENABLED = s3_settings.S3_ENABLED
except ImportError:
    S3_ENABLED = False

router = APIRouter()
settings = get_settings()

# 允許的檔案類型
ALLOWED_IMAGE_TYPES = {"jpeg", "jpg", "png", "gif", "webp"}
ALLOWED_VOICE_TYPES = {"m4a", "mp3", "ogg", "wav", "webm"}

# 惡意檔案類型 (禁止上傳)
BLOCKED_EXTENSIONS = {
    "exe", "sh", "bat", "cmd", "ps1", "bash", "elf",
    "html", "htm", "js", "php", "asp", "jsp", "cgi",
    "sql", "sqlite", "db",
    "zip", "rar", "7z", "tar", "gz",
    "pdf", "doc", "docx", "xls", "xlsx"
}

# 魔數 (檔案頭) 驗證
IMAGE_MAGIC = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",  # WebP starts with RIFF
}

def validate_file_extension(filename: str, allowed_types: set) -> bool:
    """驗證檔案副檔名"""
    import os
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in allowed_types

def validate_file_magic(file_bytes: bytes) -> str:
    """驗證檔案魔數 (檔案頭)"""
    for magic, file_type in IMAGE_MAGIC.items():
        if file_bytes.startswith(magic):
            return file_type
    return None

# 確保上傳目錄存在
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
IMAGES_DIR = UPLOAD_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# 壓縮設置
MAX_IMAGE_SIZE = 1920  # 最大邊長
QUALITY = 85


def compress_image(file_bytes: bytes) -> bytes:
    """壓縮圖片 (同步函數，會在線程池中執行)"""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        
        # 調整大小
        if max(img.size) > MAX_IMAGE_SIZE:
            img.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE), Image.LANCZOS)
        
        # 轉為 RGB (如果需要)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # 壓縮
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=QUALITY, optimize=True)
        return output.getvalue()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"圖片處理失敗: {str(e)}")


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    order_id: int = None,
    db: AsyncSession = Depends(get_db)
):
    """上傳圖片 (支持 S3 和本地存儲)"""
    import os
    
    # 驗證檔案類型
    ext = os.path.splitext(file.filename or "")[1].lower().lstrip(".")
    
    # 檢查是否為禁止的副檔名
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不允許上傳此類型檔案")
    
    # 檢查是否為允許的圖片類型
    if not validate_file_extension(file.filename or "image.jpg", ALLOWED_IMAGE_TYPES):
        raise HTTPException(status_code=400, detail="只允許上傳 jpg, png, gif, webp 格式")
    
    # 讀取檔案
    file_bytes = await file.read()
    
    # 大小限制 (10MB)
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="圖片大小不能超過 10MB")
    
    # 魔數驗證
    detected_type = validate_file_magic(file_bytes)
    if not detected_type or detected_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="檔案格式無效或已損壞")
    
    # 壓縮圖片 (使用線程池避免阻塞事件循環)
    compressed = await asyncio.to_thread(compress_image, file_bytes)
    
    # 根據配置選擇存儲方式
    if S3_ENABLED:
        # S3 存儲
        s3_key, content_type = generate_s3_key(file.filename or "image.jpg", "images")
        url = await upload_to_s3(compressed, s3_key, content_type)
    else:
        # 本地存儲 (向後兼容)
        ext = ".jpg"
        filename = f"{uuid.uuid4()}{ext}"
        filepath = IMAGES_DIR / filename
        
        with open(filepath, "wb") as f:
            f.write(compressed)
        
        url = f"/uploads/images/{filename}"
    
    # 如果有 order_id，更新訂單
    if order_id:
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        if order:
            # 追加到現有圖片列表
            import json
            existing = json.loads(order.completion_photos) if order.completion_photos else []
            existing.append(url)
            order.completion_photos = json.dumps(existing)
            await db.commit()
    
    return success_response(data={"url": url, "storage": "s3" if S3_ENABLED else "local"}, message="上傳成功")


@router.post("/voice")
async def upload_voice(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """上傳語音備註"""
    import os
    
    # 驗證檔案類型
    ext = os.path.splitext(file.filename or "")[1].lower().lstrip(".")
    
    # 檢查是否為禁止的副檔名
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不允許上傳此類型檔案")
    
    if not validate_file_extension(file.filename or "voice.m4a", ALLOWED_VOICE_TYPES):
        raise HTTPException(status_code=400, detail="只允許上傳 m4a, mp3, ogg, wav, webm 格式")
    
    file_bytes = await file.read()
    
    # 大小限制 (5MB)
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="音頻大小不能超過 5MB")
    
    # 生成文件名
    ext = os.path.splitext(file.filename)[1] or ".m4a"
    filename = f"{uuid.uuid4()}{ext}"
    
    voice_dir = UPLOAD_DIR / "voices"
    voice_dir.mkdir(parents=True, exist_ok=True)
    filepath = voice_dir / filename
    
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    
    url = f"/uploads/voices/{filename}"
    
    return success_response(data={"url": url}, message="上傳成功")


@router.get("/images/{filename}")
async def get_image(filename: str):
    """獲取圖片"""
    filepath = IMAGES_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="圖片不存在")
    
    from fastapi.responses import FileResponse
    return FileResponse(filepath, media_type="image/jpeg")
