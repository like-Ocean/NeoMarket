from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from uuid import UUID
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from models import Category, Product, ProductCharacteristic, ProductImage, Seller
from models.product import ProductStatus
from schemas.product import ProductCreate, ProductUpdate
from services.public_service import get_product_by_id_public
from services.outbox_service import add_outbox_event
from models.sku import SKU
from helpers.product_and_sku import _generate_unique_slug
from core.config import settings


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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )

    return product


async def get_products_by_seller(
    db: AsyncSession, seller_id: UUID, 
    limit: int = 20, offset: int = 0,
    status: str | None = None,
    include_deleted: bool = False
) -> dict:
    min_price_subq = (
        select(SKU.product_id, func.min(SKU.price).label("min_price"))
        .group_by(SKU.product_id)
        .subquery()
    )
    cover_image_subq = (
        select(ProductImage.url)
        .where(ProductImage.product_id == Product.id)
        .order_by(ProductImage.ordering.asc())
        .limit(1)
        .scalar_subquery()
    )

    query = (
        select(Product, min_price_subq.c.min_price, cover_image_subq.label("cover_image"))
        .outerjoin(min_price_subq, min_price_subq.c.product_id == Product.id)
        .where(Product.seller_id == seller_id)
        .order_by(Product.created_at.desc())
    )
    if status:
        query = query.where(Product.status == status)
    if not include_deleted:
        query = query.where(Product.deleted == False)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(query.limit(limit).offset(offset))
    items = []
    for product, min_price_value, cover_image in result.all():
        items.append({
            "id": product.id,
            "title": product.title,
            "slug": product.slug,
            "status": product.status,
            "category_id": product.category_id,
            "deleted": product.deleted,
            "created_at": product.created_at,
            "min_price": int(min_price_value) if min_price_value is not None else None,
            "cover_image": cover_image,
        })

    return {
        "items": items,
        "total_count": total,
        "limit": limit,
        "offset": offset,
    }


async def create_product(db: AsyncSession, seller: Seller, data: ProductCreate) -> Product:
    if data.title is None or (isinstance(data.title, str) and data.title.strip() == ""):
        return JSONResponse(
            status_code=400, 
            content={"code": "INVALID_REQUEST", "message": "title is required"}
        )
    if not isinstance(data.title, str) or len(data.title) < 1 or len(data.title) > 255:
        return JSONResponse(
            status_code=400, 
            content={"code": "INVALID_REQUEST", "message": "title must be 1-255 characters"}
        )

    try:
        _ = UUID(str(data.category_id))
    except Exception:
        return JSONResponse(
            status_code=400, 
            content={"code": "INVALID_REQUEST", "message": "category_id must be a valid UUID"}
        )

    category_result = await db.execute(
        select(Category).where(Category.id == data.category_id)
    )
    category = category_result.scalar_one_or_none()
    if not category:
        return JSONResponse(
            status_code=400, 
            content={"code": "INVALID_REQUEST", "message": "Category not found"}
        )

    slug = data.slug or await _generate_unique_slug(db, data.title)

    product = Product(
        seller_id=seller.id,
        category_id=data.category_id,
        title=data.title,
        slug=slug,
        description=data.description or "",
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


async def update_product(db: AsyncSession, product_id, seller: Seller, data: ProductUpdate) -> Product:
    product = await get_product_by_id(db, product_id)
    if product.seller_id != seller.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа",
        )
    if product.status in {ProductStatus.HARD_BLOCKED, ProductStatus.ON_MODERATION}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Редактирование товара запрещено",
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

    old_status = product.status

    payload = data.model_dump(exclude_unset=True)
    characteristics = payload.pop("characteristics", None)
    for field, value in payload.items():
        setattr(product, field, value)

    if characteristics is not None:
        product.characteristics.clear()
        for characteristic in characteristics:
            db.add(ProductCharacteristic(
                product_id=product.id,
                name=characteristic.name,
                value=characteristic.value,
            ))

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
    return await get_product_by_id(db, product.id)


async def delete_product(db: AsyncSession, product_id, seller: Seller):
    product = await get_product_by_id(db, product_id, seller_id=seller.id)

    if product.status in {ProductStatus.HARD_BLOCKED, ProductStatus.ON_MODERATION}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Редактирование товара запрещено",
        )

    skus_result = await db.execute(
        select(SKU.id).where(SKU.product_id == product.id)
    )
    sku_ids = [str(sid) for sid in skus_result.scalars().all()]

    product.deleted = True

    await add_outbox_event(
        db=db,
        event_type="DELETED",
        target_url=f"{settings.MODERATION_SERVICE_URL}/api/v1/events/product",
        payload={
            "product_id": str(product.id),
            "seller_id": str(product.seller_id),
            "event": "DELETED",
            "date": datetime.now(timezone.utc).isoformat(),
        },
    )
    await add_outbox_event(
        db=db,
        event_type="PRODUCT_DELETED",
        target_url=settings.B2C_SERVICE_URL,
        payload={
            "event": "PRODUCT_DELETED",
            "product_id": str(product.id),
            "sku_ids": sku_ids,
            "date": datetime.now(timezone.utc).isoformat(),
        },
    )

    await db.commit()


async def get_product_skus(db: AsyncSession, product_id: UUID, seller_id: UUID) -> list[SKU]:
    product = await get_product_by_id(db, product_id, seller_id=seller_id)
    result = await db.execute(
        select(SKU)
        .options(
            selectinload(SKU.images),
            selectinload(SKU.characteristics),
        )
        .where(SKU.product_id == product.id)
    )
    return result.scalars().all()


async def get_similar_products(db: AsyncSession,  product_id: UUID, limit: int = 10) -> list[Product]:
    product = await get_product_by_id_public(db, product_id)
    if not product:
        return []
    
    result = await db.execute(
        select(Product)
        .where(Product.category_id == product.category_id)
        .where(Product.id != product_id)
        .where(Product.status == ProductStatus.MODERATED)
        .order_by(Product.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
