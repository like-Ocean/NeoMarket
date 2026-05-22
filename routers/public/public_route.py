from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_b2c_key
from schemas.product import (
    ProductPublicResponse, ProductPublicShortResponse,
    ProductPublicPaginatedResponse, ProductBatchRequest
)
from schemas.sku import SKUPublicResponse
from services import public_service, product_service

public_router = APIRouter(
    prefix="/public",
    tags=["Public Catalog"],
    dependencies=[Depends(require_b2c_key)],
)


@public_router.get("/products", response_model=ProductPublicPaginatedResponse)
async def get_products_public(
    category_id: UUID | None = None,
    search: str | None = None,
    min_price: int | None = Query(None, ge=0, description="Минимальная цена"),
    max_price: int | None = Query(None, ge=0, description="Максимальная цена"),
    seller_id: UUID | None = None,
    sort: str = Query("created_desc", description="Сортировка"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    return await public_service.get_products_public(
        db=db, limit=limit, offset=offset,
        category_id=category_id,
        search=search, min_price=min_price,
        max_price=max_price,
        seller_id=seller_id,
        sort=sort,
    )


@public_router.get("/products/{product_id}", response_model=ProductPublicResponse)
async def get_product_public(
    product_id: UUID, db: AsyncSession = Depends(get_db)
):
    product = await public_service.get_product_by_id_public(db, product_id)
    if not product:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=404,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "Товар не найден"}
        )
    return product


@public_router.post("/products/batch", response_model=list[ProductPublicResponse])
async def get_products_public_batch(
    data: ProductBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    return await public_service.get_products_public_batch(db, data.product_ids)


@public_router.get("/products/{product_id}/similar", response_model=list[ProductPublicShortResponse])
async def get_similar_products_public(
    product_id: UUID,
    limit: int = Query(10, ge=1, le=50, description="Количество похожих товаров"),
    db: AsyncSession = Depends(get_db)
):
    return await product_service.get_similar_products(db, product_id, limit)


@public_router.get("/skus/{sku_id}", response_model=SKUPublicResponse)
async def get_sku_public(
    sku_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    sku = await public_service.get_sku_by_id_public(db, sku_id)
    if not sku:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=404,
            detail={"code": "SKU_NOT_FOUND", "message": "SKU не найден"}
        )
    return sku