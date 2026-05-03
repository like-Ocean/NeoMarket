from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from models.sku import SKU
from models.sku_image import SKUImage
from models.sku_characteristic import SKUCharacteristic
from models.product import Product, ProductStatus
from models.seller import Seller
from schemas.sku import SKUCreate, SKUUpdate
from services.outbox_service import add_outbox_event
from core.config import settings


async def get_sku_by_id(db: AsyncSession, sku_id, seller_id=None) -> SKU:
    result = await db.execute(
        select(SKU)
        .options(
            selectinload(SKU.images),
            selectinload(SKU.characteristics),
        )
        .where(SKU.id == sku_id)
    )
    sku = result.scalar_one_or_none()
    if not sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU не найден",
        )

    if seller_id is not None:
        product_result = await db.execute(
            select(Product).where(Product.id == sku.product_id)
        )
        product = product_result.scalar_one_or_none()
        if not product or product.seller_id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKU не найден",
            )

    return sku


async def get_skus_by_product(db: AsyncSession, product_id, seller_id) -> list[SKU]:
    product_result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = product_result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )
    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )

    result = await db.execute(
        select(SKU)
        .options(
            selectinload(SKU.images),
            selectinload(SKU.characteristics),
        )
        .where(SKU.product_id == product_id)
    )

    return result.scalars().all()


async def create_sku(db: AsyncSession, seller: Seller, data: SKUCreate) -> SKU:
    product_result = await db.execute(
        select(Product).where(Product.id == data.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )
    if product.seller_id != seller.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )
    if product.status in {ProductStatus.HARD_BLOCKED, ProductStatus.ON_MODERATION}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Редактирование товара запрещено",
        )

    if data.article:
        existing = await db.execute(select(SKU).where(SKU.article == data.article))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU с артикулом '{data.article}' уже существует",
        )

    count_result = await db.execute(
        select(func.count(SKU.id)).where(SKU.product_id == product.id)
    )
    existing_skus = count_result.scalar_one()

    sku = SKU(
        product_id=data.product_id,
        name=data.name,
        price=data.price,
        discount=data.discount,
        cost_price=data.cost_price,
        image=data.image,
        active_quantity=0,
        reserved_quantity=0,
        article=data.article,
    )
    db.add(sku)
    await db.flush()

    for image in data.images:
        db.add(SKUImage(
            sku_id=sku.id,
            url=image.url,
            ordering=image.ordering,
        ))

    for characteristic in data.characteristics:
        db.add(SKUCharacteristic(
            sku_id=sku.id,
            name=characteristic.name,
            value=characteristic.value,
        ))

    if existing_skus == 0:
        product.status = ProductStatus.ON_MODERATION
        await add_outbox_event(
            db=db,
            event_type="CREATED",
            target_url=f"{settings.MODERATION_SERVICE_URL}/api/v1/events/product",
            payload={
                "product_id": str(product.id),
                "seller_id": str(product.seller_id),
                "event": "CREATED",
                "date": datetime.now(timezone.utc).isoformat(),
            },
        )

    await db.commit()

    return await get_sku_by_id(db, sku.id)


async def update_sku(db: AsyncSession, sku_id, seller: Seller, data: SKUUpdate) -> SKU:
    sku = await get_sku_by_id(db, sku_id, seller_id=seller.id)

    product_result = await db.execute(
        select(Product).where(Product.id == sku.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product or product.seller_id != seller.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU не найден")

    if product.status in {ProductStatus.HARD_BLOCKED, ProductStatus.ON_MODERATION}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Редактирование товара запрещено",
        )
    
    if data.article:
        existing = await db.execute(select(SKU).where(SKU.article == data.article))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"SKU с артикулом '{data.article}' уже существует",
            )

    old_status = product.status

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sku, field, value)

    if old_status in {ProductStatus.MODERATED, ProductStatus.BLOCKED}:
        product.status = ProductStatus.ON_MODERATION
        await add_outbox_event(
            db=db,
            event_type="EDITED",
            target_url=f"{settings.MODERATION_SERVICE_URL}/api/v1/events/product",
            payload={
                "product_id": str(product.id),
                "seller_id": str(product.seller_id),
                "event": "EDITED",
                "date": datetime.now(timezone.utc).isoformat(),
            },
        )

    await db.commit()
    return await get_sku_by_id(db, sku.id)


async def delete_sku(db: AsyncSession, sku_id, seller: Seller):
    sku = await get_sku_by_id(db, sku_id, seller_id=seller.id)
    product_result = await db.execute(
        select(Product).where(Product.id == sku.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product or product.seller_id != seller.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU не найден")

    if product.status in {ProductStatus.HARD_BLOCKED, ProductStatus.ON_MODERATION}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Редактирование товара запрещено",
        )
    if sku.reserved_quantity > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить SKU с резервом",
        )
    await db.delete(sku)

    await db.commit()