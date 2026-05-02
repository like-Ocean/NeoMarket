from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_seller
from models.seller import Seller
from schemas.sku import SKUCreate, SKUUpdate, SKUResponse, SKUImageResponse
from services import sku_service, image_service
from pydantic import BaseModel

sku_router = APIRouter(prefix="/skus", tags=["SKUs"])


class SKUImageUpdateRequest(BaseModel):
    url: str | None = None
    ordering: int | None = None


@sku_router.get("/by-product/{product_id}", response_model=list[SKUResponse], summary="Все SKU товара")
async def get_skus_by_product(
    product_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await sku_service.get_skus_by_product(db, product_id, current_seller.id)


@sku_router.get("/{sku_id}", response_model=SKUResponse, summary="Получить SKU")
async def get_sku(
    sku_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await sku_service.get_sku_by_id(db, sku_id, seller_id=current_seller.id)


@sku_router.post(
    "", response_model=SKUResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать SKU",
)
async def create_sku(
    data: SKUCreate, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await sku_service.create_sku(db, current_seller, data)


@sku_router.patch("/{sku_id}", response_model=SKUResponse, summary="Обновить SKU")
async def update_sku(
    sku_id: UUID, data: SKUUpdate, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await sku_service.update_sku(db, sku_id, current_seller, data)


@sku_router.delete("/{sku_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить SKU")
async def delete_sku(
    sku_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller)
):
    await sku_service.delete_sku(db, sku_id, current_seller)



@sku_router.patch(
    "/images/{image_id}", response_model=SKUImageResponse,
    summary="Обновить изображение SKU",
)
async def update_sku_image(
    image_id: UUID, data: SKUImageUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await image_service.update_sku_image(
        db=db,
        image_id=image_id,
        seller_id=current_seller.id,
        url=data.url,
        ordering=data.ordering,
    )


@sku_router.delete(
    "/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить изображение SKU",
)
async def delete_sku_image(
    image_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    await image_service.delete_sku_image(db, image_id, current_seller.id)