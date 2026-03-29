from uuid import UUID
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_seller
from models.seller import Seller
from schemas.product import ProductCreate, ProductResponse, ProductListResponse, ProductUpdate
from services import product_service

product_router = APIRouter(prefix="/products", tags=["Products"])


@product_router.get(
    "",
    response_model=ProductListResponse,
    summary="Список товаров",
)
async def get_products(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_seller),
):
    return await product_service.get_products(db, limit, offset)


@product_router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар",
)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await product_service.create_product(db, current_seller, data)


@product_router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Получить товар",
)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_seller),
):
    product = await product_service.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        )
    return product


@product_router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Обновить товар",
)
async def update_product(
    product_id: UUID,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await product_service.update_product(db, product_id, current_seller, data)


@product_router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить товар",
)
async def delete_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    await product_service.delete_product(db, product_id, current_seller)
