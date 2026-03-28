from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_seller
from models.seller import Seller
from schemas.seller import SellerUpdate, SellerResponse
from services import seller_service

seller_router = APIRouter(prefix="/seller", tags=["Seller"])


@seller_router.get("/profile", response_model=SellerResponse, summary="Мой профиль")
async def get_my_data(current_seller: Seller = Depends(get_current_seller)):
    return current_seller


@seller_router.patch(
    "/profile/update", response_model=SellerResponse,
    summary="Обновить профиль",
)
async def update_me(
    data: SellerUpdate, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await seller_service.update_seller(db, current_seller, data)


@seller_router.delete(
    "/profile/delete", status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить аккаунт",
)
async def delete_me(
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    await seller_service.delete_seller(db, current_seller)
