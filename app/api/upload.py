"""圖片/語音上傳 — 需要認證"""
import asyncio, logging, os, uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from PIL import Image
import io

from app.core.auth     import get_current_user, TokenData
from app.core.database import get_db
from app.core.response import success_response
from app.core.config   import get_settings
from app.models.models import Order

try:
    from app.core.s3 import upload_to_s3, generate_s3_key, settings as s3_settings
    S3_ENABLED = s3_settings.S3_ENABLED
except ImportError:
    S3_ENABLED = False

logger   = logging.getLogger(__name__)
router   = APIRouter()
settings = get_settings()

ALLOWED_IMAGE = {"jpeg", "jpg", "png", "gif", "webp"}
ALLOWED_VOICE = {"m4a", "mp3", "ogg", "wav", "webm"}
BLOCKED_EXT   = {"exe","sh","bat","cmd","ps1","bash","elf","html","htm","js","php","asp","jsp",
                  "cgi","sql","sqlite","db","zip","rar","7z","tar","gz","pdf","doc","docx","xls","xlsx"}
IMAGE_MAGIC   = {b"\xff\xd8\xff":"jpeg", b"\x89PNG":"png", b"GIF87a":"gif", b"GIF89a":"gif", b"RIFF":"webp"}

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
IMAGES_DIR = UPLOAD_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
MAX_IMAGE  = 1920
QUALITY    = 85


def _ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower().lstrip(".")

def _magic(data: bytes) -> str | None:
    for magic, ft in IMAGE_MAGIC.items():
        if data.startswith(magic):
            return ft
    return None

def _compress(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data))
    if max(img.size) > MAX_IMAGE:
        img.thumbnail((MAX_IMAGE, MAX_IMAGE), Image.LANCZOS)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=QUALITY, optimize=True)
    return buf.getvalue()


@router.post("/image")
async def upload_image(
    file:     UploadFile = File(...),
    order_id: int = None,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),     # ← auth
):
    ext = _ext(file.filename)
    if ext in BLOCKED_EXT or ext not in ALLOWED_IMAGE:
        raise HTTPException(status_code=400, detail="不允許此檔案類型")

    data = await file.read()
    if len(data) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"超過 {settings.MAX_FILE_SIZE//1048576}MB 限制")

    detected = _magic(data)
    if not detected or detected not in ALLOWED_IMAGE:
        raise HTTPException(status_code=400, detail="檔案格式無效")

    try:
        compressed = await asyncio.to_thread(_compress, data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"圖片處理失敗: {exc}")

    if S3_ENABLED:
        s3_key, ct = generate_s3_key(file.filename or "img.jpg", "images")
        url = await upload_to_s3(compressed, s3_key, ct)
    else:
        fname = f"{uuid.uuid4()}.jpg"
        (IMAGES_DIR / fname).write_bytes(compressed)
        url = f"/uploads/images/{fname}"

    if order_id:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order  = result.scalar_one_or_none()
        if order:
            import json
            existing = json.loads(order.completion_photos) if order.completion_photos else []
            existing.append(url)
            order.completion_photos = json.dumps(existing)
            await db.commit()

    return success_response(data={"url": url, "storage": "s3" if S3_ENABLED else "local"}, message="上傳成功")


@router.post("/voice")
async def upload_voice(
    file: UploadFile = File(...),
    _: TokenData = Depends(get_current_user),     # ← auth
):
    ext = _ext(file.filename)
    if ext in BLOCKED_EXT or ext not in ALLOWED_VOICE:
        raise HTTPException(status_code=400, detail="不允許此檔案類型")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="音頻超過 5MB")
    safe_ext = f".{ext}" if ext in ALLOWED_VOICE else ".m4a"
    fname    = f"{uuid.uuid4()}{safe_ext}"
    voice_dir = UPLOAD_DIR / "voices"
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / fname).write_bytes(data)
    return success_response(data={"url": f"/uploads/voices/{fname}"}, message="上傳成功")


@router.get("/images/{filename}")
async def get_image(filename: str):
    """FIX: path traversal guard"""
    safe = Path(filename).name
    if safe != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法檔名")
    fp = IMAGES_DIR / safe
    if not fp.exists():
        raise HTTPException(status_code=404, detail="圖片不存在")
    return FileResponse(fp, media_type="image/jpeg")
