from uuid import UUID
from fastapi import APIRouter, Depends, status, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import (
    get_current_seller, get_current_seller_optional,
    require_b2c_key
)
from models.seller import Seller
from schemas.image import ImageAttachRequest, ImageUpdateRequest
from schemas.product import (
    ProductCreate, ProductResponse,
    ProductPaginatedResponse, ProductUpdate, ProductImageResponse,
    ProductPublicResponse
)
from schemas.sku import SKUResponse
from services import product_service, image_service
from services import public_service


product_router = APIRouter(prefix="/products", tags=["Products"])


@product_router.get("", response_model=ProductPaginatedResponse)
async def get_products(
    limit: int = 20, offset: int = 0,
    status: str | None = None,
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await product_service.get_products_by_seller(
        db=db,
        seller_id=current_seller.id,
        limit=limit,
        offset=offset,
        status=status,
        include_deleted=include_deleted,
    )


@product_router.post(
    "", response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар"
)
async def create_product(
    data: ProductCreate, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await product_service.create_product(db, current_seller, data)


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
        await require_b2c_key(x_service_key)
        product = await public_service.get_product_by_id_public(db, product_id)
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")
        return product

    if not current_seller:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")

    return await product_service.get_product_by_id(
        db, product_id, seller_id=current_seller.id
    )


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


@product_router.get(
    "/{product_id}/skus",
    response_model=list[SKUResponse],
    summary="Все SKU товара"
)
async def list_product_skus(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await product_service.get_product_skus(
        db=db,
        product_id=product_id,
        seller_id=current_seller.id
    )


@product_router.post(
    "/{product_id}/images",
    response_model=ProductImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Прикрепить изображение к товару"
)
async def add_product_image(
    product_id: UUID, data: ImageAttachRequest,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await image_service.attach_product_image(
        db=db,
        product_id=product_id,
        seller_id=current_seller.id,
        image_id=data.image_id,
        url=data.url,
        ordering=data.ordering
    )


@product_router.patch(
    "/images/{image_id}",
    response_model=ProductImageResponse,
    summary="Обновить изображение товара",
)
async def update_product_image(
    image_id: UUID, data: ImageUpdateRequest,
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