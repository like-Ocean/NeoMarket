from uuid import UUID
from typing import Union
from fastapi import APIRouter, Depends, status, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_seller, get_current_seller_optional, require_internal_token
from core.config import settings
from models.seller import Seller
from schemas.image import ProductImageUpdateRequest
from schemas.product import (
    ProductCreate, ProductResponse,
    ProductListResponse, ProductUpdate, ProductImageResponse,
    ProductPublicListResponse, ProductPublicResponse
)
from schemas.events import ProductEventRequest
from services import product_service, image_service
from services import public_service
from services.moderation_service import handle_product_event


product_router = APIRouter(prefix="/products", tags=["Products"])


@product_router.get("", response_model=ProductListResponse | ProductPublicListResponse)
async def get_products(
    limit: int = 20, offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller | None = Depends(get_current_seller_optional),
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
):
    if x_service_key:
        if x_service_key != settings.MOD_SERVICE_KEY:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный Service Key")
        return await product_service.get_products(db, limit, offset)

    if current_seller:
        return await product_service.get_products_by_seller(db, current_seller.id, limit, offset)

    return await public_service.get_products_public(db=db, limit=limit, offset=offset)


@product_router.post(
    "", response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар",
)
async def create_product(
    data: ProductCreate, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await product_service.create_product(db, current_seller, data)


@product_router.get("/my", response_model=ProductListResponse)
async def get_my_products(
    limit: int = 20, offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await product_service.get_products_by_seller(db, current_seller.id, limit, offset)


@product_router.get(
    "/{product_id}", response_model=ProductResponse | ProductPublicResponse,
    summary="Получить товар по ID",
)
async def get_product(
    product_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller | None = Depends(get_current_seller_optional),
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
):
    if x_service_key:
        if x_service_key != settings.MOD_SERVICE_KEY:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный Service Key")
        return await product_service.get_product_by_id(db, product_id)

    if current_seller:
        return await product_service.get_product_by_id(db, product_id, seller_id=current_seller.id)

    product = await public_service.get_product_by_id_public(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")
    return product


@product_router.patch(
    "/{product_id}", response_model=ProductResponse,
    summary="Обновить товар",
)
async def update_product(
    product_id: UUID, data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await product_service.update_product(db, product_id, current_seller, data)


@product_router.put(
    "/{product_id}", response_model=ProductResponse,
    summary="Обновить товар (PUT)",
)
async def update_product_put(
    product_id: UUID, data: ProductUpdate,
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
    product_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    await product_service.delete_product(db, product_id, current_seller)


@product_router.post(
    "/events",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="События модерации товара",
)
async def product_events(
    data: ProductEventRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_internal_token),
    x_service_key: str = Header(alias="X-Service-Key"),
):
    if x_service_key != settings.MOD_SERVICE_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный Service Key")
    await handle_product_event(db, data)


@product_router.patch(
    "/images/{image_id}",
    response_model=ProductImageResponse,
    summary="Обновить изображение товара",
)
async def update_product_image(
    image_id: UUID, data: ProductImageUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await image_service.update_product_image(
        db=db, image_id=image_id,
        seller_id=current_seller.id,
        url=data.url, ordering=data.ordering,
    )


@product_router.delete(
    "/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить изображение товара",
)
async def delete_product_image(
    image_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    await image_service.delete_product_image(db, image_id, current_seller.id)