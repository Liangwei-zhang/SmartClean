"""
圖片上傳 API
"""
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

router = APIRouter()
settings = get_settings()

# 確保上傳目錄存在
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
IMAGES_DIR = UPLOAD_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# 壓縮設置
MAX_IMAGE_SIZE = 1920  # 最大邊長
QUALITY = 85


async def compress_image(file_bytes: bytes) -> bytes:
    """壓縮圖片"""
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
    """上傳圖片"""
    # 驗證文件類型
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只能上傳圖片文件")
    
    # 讀取文件
    file_bytes = await file.read()
    
    # 大小限制 (10MB)
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="圖片大小不能超過 10MB")
    
    # 壓縮圖片
    compressed = await compress_image(file_bytes)
    
    # 生成唯一文件名
    ext = ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = IMAGES_DIR / filename
    
    # 保存
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
    
    return success_response(data={"url": url}, message="上傳成功")


@router.post("/voice")
async def upload_voice(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """上傳語音備註"""
    if not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="只能上傳音頻文件")
    
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
