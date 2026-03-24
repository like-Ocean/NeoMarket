import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(seller_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": seller_id,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> str:
    """Возвращает seller_id или выбрасывает JWTError"""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    if payload.get("type") != "access":
        raise JWTError("Wrong token type")

    seller_id: str | None = payload.get("sub")
    if seller_id is None:
        raise JWTError("Missing subject")

    return seller_id


def generate_refresh_token() -> str:
    """случайный токен — просто случайная строка"""
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """Храним хэш, не сам токен"""
    return hashlib.sha256(token.encode()).hexdigest()
