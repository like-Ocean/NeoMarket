from fastapi import Depends, HTTPException, status, Header
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.security import decode_access_token
from core.config import settings
from models.seller import Seller
from services.seller_service import get_seller_by_id

def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не передан Authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный формат Authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.split(" ", 1)[1]


async def get_current_seller(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> Seller:
    token = _extract_bearer_token(authorization)
    try:
        seller_id = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    seller = await get_seller_by_id(db, seller_id)
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Продавец не найден",
        )

    return seller


async def get_current_seller_optional(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db)
) -> Seller | None:
    if not authorization:
        return None
    token = _extract_bearer_token(authorization)
    try:
        seller_id = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    seller = await get_seller_by_id(db, seller_id)
    if not seller:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Продавец не найден")
    return seller


def require_service_key(x_service_key: str | None = Header(default=None, alias="X-Service-Key")) -> str:
    if not x_service_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Service-Key обязателен")
    return x_service_key


def require_moderation_key(x_service_key: str = Depends(require_service_key)) -> None:
    if x_service_key != settings.MOD_SERVICE_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный Service Key")


def require_b2c_key(x_service_key: str = Depends(require_service_key)) -> None:
    if x_service_key != settings.B2C_SERVICE_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный Service Key")


def require_internal_token(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> None:
    if not x_internal_token or x_internal_token != settings.INTERNAL_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Неверный внутренний токен",
        )
