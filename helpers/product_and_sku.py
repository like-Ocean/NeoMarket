from uuid import UUID
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from models.sku import SKU
from models.sku_image import SKUImage
from models.product_image import ProductImage
from models.product import Product
from models.uploaded_image import UploadedImage


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



async def _resolve_uploaded_image(db: AsyncSession, image_id: UUID, entity_type: str) -> UploadedImage:
    result = await db.execute(
        select(UploadedImage).where(UploadedImage.id == image_id)
    )
    uploaded = result.scalar_one_or_none()
    if not uploaded:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено")
    if uploaded.entity_type != entity_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный тип изображения",
        )
    
    return uploaded


def _slugify(title: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    if not cleaned:
        return "product"
    return cleaned.replace(" ", "-")


async def _generate_unique_slug(db: AsyncSession, title: str) -> str:
    base = _slugify(title)
    slug = base
    suffix = 2

    while True:
        result = await db.execute(select(Product.id).where(Product.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1