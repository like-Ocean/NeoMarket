from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from services.file_service import delete_file_from_disk
from models.sku import SKU
from models.sku_image import SKUImage
from models.product_image import ProductImage
from models.product import Product


async def _get_product_for_seller(db: AsyncSession, product_id: UUID, seller_id: UUID) -> Product:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")
    if product.seller_id != seller_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа")
    return product


async def _get_sku_for_seller(db: AsyncSession, sku_id: UUID, seller_id: UUID) -> SKU:
    result = await db.execute(select(SKU).where(SKU.id == sku_id))
    sku = result.scalar_one_or_none()
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU не найден")

    await _get_product_for_seller(db, sku.product_id, seller_id)
    return sku


async def _get_product_image(db: AsyncSession, image_id: UUID, seller_id: UUID) -> ProductImage:
    result = await db.execute(
        select(ProductImage).where(ProductImage.id == image_id)
    )
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено")

    product_result = await db.execute(
        select(Product).where(Product.id == image.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product or product.seller_id != seller_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа")

    return image


async def _get_sku_image(db: AsyncSession, image_id: UUID, seller_id: UUID) -> SKUImage:
    result = await db.execute(
        select(SKUImage).where(SKUImage.id == image_id)
    )
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено")

    sku_result = await db.execute(
        select(SKU).where(SKU.id == image.sku_id)
    )
    sku = sku_result.scalar_one_or_none()
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU не найден")

    product_result = await db.execute(
        select(Product).where(Product.id == sku.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product or product.seller_id != seller_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа")

    return image


async def add_product_image(
    db: AsyncSession, product_id: UUID,
    seller_id: UUID, url: str,
    ordering: int = 0,
) -> ProductImage:
    await _get_product_for_seller(db, product_id, seller_id)

    image = ProductImage(product_id=product_id, url=url, ordering=ordering)
    db.add(image)
    await db.commit()
    await db.refresh(image)
    return image


async def add_sku_image(
    db: AsyncSession, sku_id: UUID,
    seller_id: UUID, url: str,
    ordering: int = 0,
) -> SKUImage:
    await _get_sku_for_seller(db, sku_id, seller_id)

    image = SKUImage(sku_id=sku_id, url=url, ordering=ordering)
    db.add(image)
    await db.commit()
    await db.refresh(image)
    return image


async def update_product_image(
    db: AsyncSession, image_id: UUID,
    seller_id: UUID, url: str | None = None,
    ordering: int | None = None,
) -> ProductImage:
    if url is None and ordering is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужно передать хотя бы одно поле: url или ordering",
        )

    image = await _get_product_image(db, image_id, seller_id)
    if url is not None:
        image.url = url
    if ordering is not None:
        image.ordering = ordering

    await db.commit()
    await db.refresh(image)
    return image


async def update_sku_image(
    db: AsyncSession, image_id: UUID,
    seller_id: UUID, url: str | None = None,
    ordering: int | None = None,
) -> SKUImage:
    if url is None and ordering is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужно передать хотя бы одно поле: url или ordering",
        )

    image = await _get_sku_image(db, image_id, seller_id)
    if url is not None:
        image.url = url
    if ordering is not None:
        image.ordering = ordering

    await db.commit()
    await db.refresh(image)
    return image


async def update_product_image_ordering(
    db: AsyncSession, image_id: UUID,
    ordering: int, seller_id: UUID
) -> ProductImage:
    return await update_product_image(
        db=db,
        image_id=image_id,
        seller_id=seller_id,
        ordering=ordering,
    )


async def delete_product_image(db: AsyncSession, image_id: UUID, seller_id: UUID):
    image = await _get_product_image(db, image_id, seller_id)
    url = image.url
    
    await db.delete(image)
    await db.commit()
    
    delete_file_from_disk(url)


async def update_sku_image_ordering(
    db: AsyncSession, image_id: UUID,
    ordering: int, seller_id: UUID
) -> SKUImage:
    return await update_sku_image(
        db=db,
        image_id=image_id,
        seller_id=seller_id,
        ordering=ordering,
    )


async def delete_sku_image(db: AsyncSession, image_id: UUID, seller_id: UUID):
    image = await _get_sku_image(db, image_id, seller_id)
    url = image.url
    
    await db.delete(image)
    await db.commit()
    
    delete_file_from_disk(url)