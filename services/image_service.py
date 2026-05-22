from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from services.file_service import delete_file_from_disk
from models.sku import SKU
from models.product import ProductStatus, Product
from models.sku_image import SKUImage
from models.product_image import ProductImage
from helpers.product_and_sku import (
    _get_product_for_seller, _get_sku_for_seller,
    _get_product_image, _get_sku_image, _resolve_uploaded_image
)
from models.uploaded_image import UploadedImage
from services.outbox_service import add_outbox_event
from core.config import settings


async def _maybe_send_product_to_moderation(db: AsyncSession, product: Product):
    """Если продукт был MODERATED или BLOCKED, переводим в ON_MODERATION и шлём событие EDITED."""
    if product.status in {ProductStatus.MODERATED, ProductStatus.BLOCKED}:
        product.status = ProductStatus.ON_MODERATION
        await add_outbox_event(
            db=db, event_type="EDITED",
            target_url=f"{settings.MODERATION_SERVICE_URL}/api/v1/events/product",
            payload={
                "product_id": str(product.id),
                "seller_id": str(product.seller_id),
                "event": "EDITED",
                "date": datetime.now(timezone.utc).isoformat(),
            },
        )

async def add_product_image(
    db: AsyncSession, product_id: UUID,
    seller_id: UUID, url: str, ordering: int = 0
) -> ProductImage:
    product = await _get_product_for_seller(db, product_id, seller_id)
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403, 
            detail={"code": "FORBIDDEN", "message": "Редактирование запрещено"}
        )

    image = ProductImage(product_id=product_id, url=url, ordering=ordering)
    db.add(image)
    await _maybe_send_product_to_moderation(db, product)
    await db.commit()
    await db.refresh(image)
    return image


async def create_uploaded_image(
    db: AsyncSession, url: str,
    entity_type: str, entity_id: UUID | None,
    ordering: int = 0
) -> UploadedImage:
    uploaded = UploadedImage(
        url=url,
        entity_type=entity_type,
        entity_id=entity_id,
        ordering=ordering
    )
    db.add(uploaded)
    
    await db.commit()
    await db.refresh(uploaded)
    
    return uploaded


async def attach_product_image(
    db: AsyncSession, product_id: UUID,
    seller_id: UUID, image_id: UUID | None,
    url: str | None, ordering: int = 0
) -> ProductImage:
    product = await _get_product_for_seller(db, product_id, seller_id)
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Редактирование запрещено"}
        )

    if image_id:
        uploaded = await _resolve_uploaded_image(db, image_id, "PRODUCT")
        url = uploaded.url
        ordering = uploaded.ordering if ordering == 0 else ordering
        await db.delete(uploaded)

    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_REQUEST", "message": "Нужно передать image_id или url"},
        )

    image = ProductImage(product_id=product_id, url=url, ordering=ordering)
    db.add(image)
    await _maybe_send_product_to_moderation(db, product)
    await db.commit()
    await db.refresh(image)

    return image


async def attach_sku_image(
    db: AsyncSession, sku_id: UUID,
    seller_id: UUID, image_id: UUID | None,
    url: str | None, ordering: int = 0
) -> SKUImage:
    sku = await _get_sku_for_seller(db, sku_id, seller_id)
    product = await _get_product_for_seller(db, sku.product_id, seller_id)
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403, 
            detail={"code": "FORBIDDEN", "message": "Редактирование запрещено"}
        )

    if image_id:
        uploaded = await _resolve_uploaded_image(db, image_id, "SKU")
        url = uploaded.url
        ordering = uploaded.ordering if ordering == 0 else ordering
        await db.delete(uploaded)

    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_REQUEST", "message": "Нужно передать image_id или url"
            },
        )

    image = SKUImage(sku_id=sku_id, url=url, ordering=ordering)
    db.add(image)
    await _maybe_send_product_to_moderation(db, product)
    await db.commit()
    await db.refresh(image)
    return image


async def add_sku_image(db: AsyncSession, sku_id: UUID, seller_id: UUID, url: str, ordering: int = 0) -> SKUImage:
    sku = await _get_sku_for_seller(db, sku_id, seller_id)
    product = await _get_product_for_seller(db, sku.product_id, seller_id)
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Редактирование запрещено"}
        )

    image = SKUImage(sku_id=sku_id, url=url, ordering=ordering)
    db.add(image)
    await _maybe_send_product_to_moderation(db, product)
    await db.commit()
    await db.refresh(image)
    return image


async def update_sku_image(
    db: AsyncSession, image_id: UUID,
    seller_id: UUID, url: str | None = None,
    ordering: int | None = None
) -> SKUImage:
    if url is None and ordering is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_REQUEST", "message": "Нужно передать хотя бы одно поле: url или ordering"
            },
        )

    image = await _get_sku_image(db, image_id, seller_id)
    sku = await _get_sku_for_seller(db, image.sku_id, seller_id)
    product = await _get_product_for_seller(db, sku.product_id, seller_id)
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Редактирование запрещено"}
        )

    if url is not None:
        image.url = url
    if ordering is not None:
        image.ordering = ordering

    await _maybe_send_product_to_moderation(db, product)
    await db.commit()
    await db.refresh(image)
    return image



async def update_product_image(
    db: AsyncSession, image_id: UUID,
    seller_id: UUID, url: str | None = None,
    ordering: int | None = None
) -> ProductImage:
    if url is None and ordering is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_REQUEST", "message": "Нужно передать хотя бы одно поле: url или ordering"
            },
        )

    image = await _get_product_image(db, image_id, seller_id)
    product = await _get_product_for_seller(db, image.product_id, seller_id)
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Редактирование запрещено"}
        )

    if url is not None:
        image.url = url
    if ordering is not None:
        image.ordering = ordering

    await _maybe_send_product_to_moderation(db, product)
    await db.commit()
    await db.refresh(image)
    return image


async def delete_product_image(db: AsyncSession, image_id: UUID, seller_id: UUID):
    image = await _get_product_image(db, image_id, seller_id)
    product = await _get_product_for_seller(db, image.product_id, seller_id)
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403, detail={"code": "FORBIDDEN", "message": "Редактирование запрещено"}
        )

    url = image.url
    await db.delete(image)
    await _maybe_send_product_to_moderation(db, product)
    await db.commit()
    delete_file_from_disk(url)


async def update_sku_image_ordering(
    db: AsyncSession, image_id: UUID,
    ordering: int, seller_id: UUID
) -> SKUImage:
    return await update_sku_image(
        db=db, image_id=image_id,
        seller_id=seller_id,
        ordering=ordering
    )


async def delete_sku_image(db: AsyncSession, image_id: UUID, seller_id: UUID):
    image = await _get_sku_image(db, image_id, seller_id)
    sku = await _get_sku_for_seller(db, image.sku_id, seller_id)
    product = await _get_product_for_seller(db, sku.product_id, seller_id)
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Редактирование запрещено"}
        )
    url = image.url
    await db.delete(image)
    await _maybe_send_product_to_moderation(db, product)
    await db.commit()
    delete_file_from_disk(url)