"""
JWT 認證中間件 — 無 DB 查詢，Redis 撤銷校驗
所有敏感端點通過 Depends(require_cleaner) / Depends(require_host) 保護
"""
import logging
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt, ExpiredSignatureError

from app.core.config import get_settings
from app.core.websocket import get_redis

logger   = logging.getLogger(__name__)
settings = get_settings()
security = HTTPBearer(auto_error=False)


class TokenData:
    __slots__ = ("user_id", "user_type")
    def __init__(self, user_id: int, user_type: str):
        self.user_id   = user_id
        self.user_type = user_type


async def _decode_token(token: str) -> TokenData:
    """Validate JWT + Redis revocation list. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 已過期")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 無效")

    user_id   = payload.get("sub")
    user_type = payload.get("type")
    if not user_id or not user_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 格式錯誤")

    # Check revocation list (O(1), no DB hit)
    r = await get_redis()
    if r:
        try:
            if await r.get(f"token_revoked:{token}"):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 已撤銷")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Redis revocation check failed: %s", exc)

    return TokenData(user_id=int(user_id), user_type=user_type)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenData:
    """Any valid token (cleaner or host)."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少認證 Token")
    return await _decode_token(credentials.credentials)


async def require_cleaner(token: TokenData = Depends(get_current_user)) -> TokenData:
    if token.user_type != "cleaner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要清潔員權限")
    return token


async def require_host(token: TokenData = Depends(get_current_user)) -> TokenData:
    if token.user_type not in ("host", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要房東權限")
    return token


async def require_admin(token: TokenData = Depends(get_current_user)) -> TokenData:
    """Admin = host-type user with special flag. For now hosts can access admin."""
    if token.user_type not in ("host", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理員權限")
    return token


# ── Optional auth (public read, auth write) ──────────────────────────────────
async def optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenData]:
    """Returns None if no token, TokenData if valid."""
    if not credentials:
        return None
    try:
        return await _decode_token(credentials.credentials)
    except HTTPException:
        return None


# ── Internal bearer (for inter-service / admin script calls) ─────────────────
async def require_bearer(authorization: Optional[str] = Header(None)) -> None:
    """Validate X_BEARER_TOKEN for internal endpoints (monitoring, etc.)."""
    expected = settings.X_BEARER_TOKEN
    if not expected:
        return  # Bearer auth disabled when token not configured
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Bearer Token")
    import secrets
    if not secrets.compare_digest(authorization.split(" ", 1)[1], expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bearer Token 無效")
