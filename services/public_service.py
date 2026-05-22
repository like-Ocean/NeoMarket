from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import UUID, select, func, or_, exists
from models.product_characteristic import ProductCharacteristic
from sqlalchemy.orm import selectinload
from models import Product, SKU, ProductImage
from models.product import ProductStatus


async def get_products_public(
    db: AsyncSession, limit: int = 20,
    offset: int = 0, category_id: UUID | None = None,
    filters: dict | None = None,
    search: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    seller_id: UUID | None = None,
    sort: str = "created_desc"
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
        .join(SKU, SKU.product_id == Product.id)
        .join(min_price_subq, min_price_subq.c.product_id == Product.id)
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
    
    if min_price is not None:
        query = query.where(min_price_subq.c.min_price >= min_price)
    if max_price is not None:
        query = query.where(min_price_subq.c.min_price <= max_price)

    if filters:
        for attr_name, values in filters.items():
            if not isinstance(values, list):
                values = [values]
            values = [v for v in values if v]
            if not values:
                continue
            subq = select(ProductCharacteristic).where(
                ProductCharacteristic.product_id == Product.id,
                ProductCharacteristic.name == attr_name,
                ProductCharacteristic.value.in_(values)
            )
            query = query.where(exists(subq))

    if sort == "price_asc":
        query = query.order_by(min_price_subq.c.min_price.asc())
    elif sort == "price_desc":
        query = query.order_by(min_price_subq.c.min_price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    total = await db.execute(select(func.count()).select_from(query.subquery()))
    total_count = total.scalar_one()

    result = await db.execute(query.offset(offset).limit(limit))
    items = []
    for product, min_price_value, cover_image in result.all():
        items.append({
            "id": product.id,
            "title": product.title,
            "slug": product.slug,
            "status": product.status,
            "category_id": product.category_id,
            "min_price": int(min_price_value) if min_price_value is not None else 0,
            "cover_image": cover_image,
            "created_at": product.created_at,
        })

    return {
        "items": items,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
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


async def get_products_public_batch(db: AsyncSession, product_ids: list[UUID]) -> list[Product]:
    if not product_ids:
        return []
    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.characteristics),
            selectinload(Product.skus).options(
                selectinload(SKU.images),
                selectinload(SKU.characteristics),
            ),
        )
        .where(Product.id.in_(product_ids))
        .where(Product.status == ProductStatus.MODERATED)
        .where(Product.deleted == False)
    )
    products = result.scalars().all()
    visible = []
    for product in products:
        product.skus = [sku for sku in product.skus if sku.active_quantity > 0]
        if product.skus:
            visible.append(product)
    return visible


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