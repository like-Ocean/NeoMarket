import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
import bcrypt
from core.config import settings


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_byte = plain_password.encode('utf-8')
    hashed_byte = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte, hashed_byte)


def create_access_token(seller_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": seller_id,
        "exp": expire,
        "type": "access",
    }
    secret = settings.JWT_SECRET if settings.JWT_SECRET else settings.SECRET_KEY
    algorithm = settings.JWT_ALGORITHM if settings.JWT_ALGORITHM else settings.ALGORITHM
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str) -> str:
    secret = settings.JWT_SECRET if settings.JWT_SECRET else settings.SECRET_KEY
    algorithm = settings.JWT_ALGORITHM if settings.JWT_ALGORITHM else settings.ALGORITHM
    payload = jwt.decode(token, secret, algorithms=[algorithm])

    if payload.get("type") != "access":
        raise JWTError("Wrong token type")

    seller_id: str | None = payload.get("sub")
    if seller_id is None:
        raise JWTError("Missing subject")

    return seller_id


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
