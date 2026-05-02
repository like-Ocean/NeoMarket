from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models import Seller
from schemas.seller import SellerCreate, SellerUpdate
from core.security import hash_password


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_seller_by_id(db: AsyncSession, seller_id) -> Seller | None:
    result = await db.execute(select(Seller).where(Seller.id == seller_id))
    return result.scalar_one_or_none()


async def get_seller_by_email(db: AsyncSession, email: str) -> Seller | None:
    normalized_email = normalize_email(email)
    result = await db.execute(
        select(Seller).where(func.lower(Seller.email) == normalized_email)
    )
    return result.scalar_one_or_none()


async def create_seller(db: AsyncSession, data: SellerCreate) -> Seller:
    seller = Seller(
        email=normalize_email(str(data.email)),
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        middle_name=data.middle_name,
        company_name=data.company_name,
        inn=data.inn,
        phone=data.phone,
    )
    db.add(seller)
    await db.flush()
    return seller


async def update_seller(db: AsyncSession, seller: Seller, data: SellerUpdate) -> Seller:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(seller, field, value)
    await db.commit()
    await db.refresh(seller)
    return seller


# TODO: сделать флаг is_deleted для того чтобы не удалять пользователей
async def delete_seller(db: AsyncSession, seller: Seller) -> None:
    await db.delete(seller)
    await db.commit()
