from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from services import category_service, public_service, product_service

public_router = APIRouter(prefix="/public", tags=["Public Catalog"])


@public_router.get("/categories/tree")
async def get_categories_tree(
    db: AsyncSession = Depends(get_db),
):
    return await category_service.get_categories_tree(db)


@public_router.get("/categories/{category_id}/breadcrumbs")
async def get_breadcrumbs(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await category_service.get_breadcrumbs(db, category_id)


@public_router.get("/products")
async def get_products_public(
    category_id: UUID | None = None,
    search: str | None = None,
    min_price: int | None = Query(None, ge=0, description="Минимальная цена"),
    max_price: int | None = Query(None, ge=0, description="Максимальная цена"),
    seller_id: UUID | None = None,
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(20, ge=1, le=100, description="Товаров на странице"),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    return await public_service.get_products_public(
        db=db, limit=size, offset=offset,
        category_id=category_id,
        search=search, min_price=min_price,
        max_price=max_price,
        seller_id=seller_id,
    )


@public_router.get("/products/{product_id}")
async def get_product_public(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    product = await public_service.get_product_by_id_public(db, product_id)
    if not product:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден"
        )
    return product


@public_router.get("/products/{product_id}/similar")
async def get_similar_products_public(
    product_id: UUID,
    limit: int = Query(10, ge=1, le=50, description="Количество похожих товаров"),
    db: AsyncSession = Depends(get_db),
):
    return await product_service.get_similar_products(db, product_id, limit)


@public_router.get("/skus/{sku_id}")
async def get_sku_public(
    sku_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    sku = await public_service.get_sku_by_id_public(db, sku_id)
    if not sku:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SKU не найден"
        )
    return sku