from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.seller import Seller
from schemas.seller import SellerCreate, SellerUpdate
from core.security import hash_password


async def get_seller_by_id(db: AsyncSession, seller_id) -> Seller | None:
    result = await db.execute(select(Seller).where(Seller.id == seller_id))
    return result.scalar_one_or_none()


async def get_seller_by_email(db: AsyncSession, email: str) -> Seller | None:
    result = await db.execute(select(Seller).where(Seller.email == email))
    return result.scalar_one_or_none()


async def create_seller(db: AsyncSession, data: SellerCreate) -> Seller:
    seller = Seller(
        email=data.email,
        password_hash=hash_password(data.password),
        company_name=data.company_name,
        phone=data.phone,
    )
    db.add(seller)
    await db.flush()
    return seller


async def update_seller(db: AsyncSession, seller: Seller, data: SellerUpdate) -> Seller:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(seller, field, value)
    await db.flush()
    return seller


async def delete_seller(db: AsyncSession, seller: Seller) -> None:
    await db.delete(seller)
