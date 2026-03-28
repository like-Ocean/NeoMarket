from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from models.seller import Seller
from models.refresh_token import RefreshToken
from schemas.auth import LoginRequest, TokenResponse
from schemas.seller import SellerCreate
from core.security import (
    verify_password, create_access_token,
    generate_refresh_token, hash_refresh_token,
)
from core.config import settings
from services.seller_service import get_seller_by_email, get_seller_by_id, create_seller


async def register(db: AsyncSession, data: SellerCreate) -> Seller:
    existing = await get_seller_by_email(db, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Продавец с таким email уже существует",
        )

    new_seller = await create_seller(db, data)
    await db.commit()
    await db.refresh(new_seller)

    return new_seller


async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
    seller = await get_seller_by_email(db, email)
    if not seller or not verify_password(password, seller.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )
    return await _issue_tokens(db, seller)


async def refresh_tokens(db: AsyncSession, raw_token: str) -> TokenResponse:
    token_hash = hash_refresh_token(raw_token)

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    db_token = result.scalar_one_or_none()

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или истёкший refresh token",
        )

    db_token.revoked = True
    await db.commit()

    seller = await get_seller_by_id(db, db_token.seller_id)
    return await _issue_tokens(db, seller)


async def logout(db: AsyncSession, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()

    if db_token:
        db_token.revoked = True
        await db.commit()


async def _issue_tokens(db: AsyncSession, seller: Seller) -> TokenResponse:
    access_token = create_access_token(str(seller.id))
    raw_refresh = generate_refresh_token()

    db.add(RefreshToken(
        seller_id=seller.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
    ))

    result = await db.execute(
        select(RefreshToken.id)
        .where(RefreshToken.seller_id == seller.id)
        .order_by(RefreshToken.created_at.asc())
    )
    all_token_ids = result.scalars().all()
    if len(all_token_ids) > 5:
        ids_to_delete = all_token_ids[:len(all_token_ids) - 5]
        await db.execute(
            delete(RefreshToken).where(RefreshToken.id.in_(ids_to_delete))
        )

    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
    )

