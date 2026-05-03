from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import UUID, select, func, or_
from sqlalchemy.orm import selectinload
from models import Product, SKU
from models.product import ProductStatus


async def get_products_public(
    db: AsyncSession, limit: int = 20,
    offset: int = 0, category_id: UUID | None = None,
    search: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    seller_id: UUID | None = None,
) -> dict:
    query = (
        select(Product)
        .join(SKU, SKU.product_id == Product.id)
        .where(Product.status == ProductStatus.MODERATED)
        .where(Product.deleted == False)
        .where(SKU.active_quantity > 0)
        .distinct()
    )
    if category_id:
        query = query.where(Product.category_id == category_id)
    
    if seller_id:
        query = query.where(Product.seller_id == seller_id)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Product.title.ilike(search_pattern),
                Product.description.ilike(search_pattern)
            )
        )
    
    if min_price is not None or max_price is not None:
        min_price_subq = (
            select(SKU.product_id, func.min(SKU.price).label("min_price"))
            .group_by(SKU.product_id)
            .subquery()
        )
        
        query = query.join(
            min_price_subq, 
            Product.id == min_price_subq.c.product_id
        )
        
        if min_price is not None:
            query = query.where(min_price_subq.c.min_price >= min_price)
        if max_price is not None:
            query = query.where(min_price_subq.c.min_price <= max_price)

    total = await db.execute(select(func.count()).select_from(query.subquery()))
    total_count = total.scalar_one()
    
    query = query.order_by(Product.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    items = result.scalars().all()
    
    return {
        "total": total_count,
        "items": items,
        "page": (offset // limit) + 1 if limit > 0 else 1,
        "size": limit
    }


async def get_product_by_id_public(db: AsyncSession, product_id: UUID) -> Product | None:
    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.characteristics),
            selectinload(Product.skus).options(
                selectinload(SKU.images),
                selectinload(SKU.characteristics)
            ),
        )
        .where(Product.id == product_id)
        .where(Product.status == ProductStatus.MODERATED)
        .where(Product.deleted == False)
    )
    product = result.scalar_one_or_none()
    if not product:
        return None
    
    product.skus = [sku for sku in product.skus if sku.active_quantity > 0]
    return product


async def get_sku_by_id_public(db: AsyncSession, sku_id: UUID) -> SKU | None:
    result = await db.execute(
        select(SKU)
        .options(
            selectinload(SKU.images),
            selectinload(SKU.characteristics),
            selectinload(SKU.product),
        )
        .where(SKU.id == sku_id)
    )
    sku = result.scalar_one_or_none()
    if not sku:
        return None

    if sku.product.status != ProductStatus.MODERATED or sku.product.deleted:
        return None
    if sku.active_quantity <= 0:
        return None
    
    return sku