from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID
from fastapi import HTTPException, status
from models import Category, Product, ProductCharacteristic, ProductImage, Seller
from schemas.product import ProductCreate, ProductUpdate


async def get_product_by_id(db: AsyncSession, product_id, seller_id=None) -> Product | None:
    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.characteristics),
            selectinload(Product.skus),
        )
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )

    if seller_id is not None and product.seller_id != seller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к товару",
        )

    return product


async def get_products(db: AsyncSession, seller_id: UUID, limit: int = 20, offset: int = 0) -> dict:
    total_result = await db.execute(
        select(func.count(Product.id)).where(Product.seller_id == seller_id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(Product)
        .where(Product.seller_id == seller_id)
        .order_by(Product.created_at.desc())
        .limit(limit).offset(offset)
    )

    return {
        "total": total,
        "items": result.scalars().all(),
    }


async def create_product(db: AsyncSession, seller: Seller, data: ProductCreate) -> Product:
    category_result = await db.execute(
        select(Category).where(Category.id == data.category_id)
    )
    category = category_result.scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        )

    product = Product(
        seller_id=seller.id,
        category_id=data.category_id,
        title=data.title,
        description=data.description,
    )
    db.add(product)
    await db.flush()

    for image in data.images:
        db.add(ProductImage(
            product_id=product.id,
            url=image.url,
            ordering=image.ordering,
        ))

    for characteristic in data.characteristics:
        db.add(ProductCharacteristic(
            product_id=product.id,
            name=characteristic.name,
            value=characteristic.value,
        ))

    await db.commit()
    return await get_product_by_id(db, product.id)


async def update_product(
        db: AsyncSession, product_id,
        seller: Seller, data: ProductUpdate,
) -> Product:
    product = await get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )

    if product.seller_id != seller.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к товару",
        )

    if data.category_id is not None:
        category_result = await db.execute(
            select(Category).where(Category.id == data.category_id)
        )
        category = category_result.scalar_one_or_none()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Категория не найдена",
            )

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    await db.commit()
    return await get_product_by_id(db, product.id)


async def delete_product(db: AsyncSession, product_id, seller: Seller) -> None:
    product = await get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )

    if product.seller_id != seller.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к товару",
        )

    await db.delete(product)
    await db.commit()
