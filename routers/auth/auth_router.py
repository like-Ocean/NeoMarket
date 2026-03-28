from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from schemas.auth import TokenResponse, RefreshRequest
from fastapi.security import OAuth2PasswordRequestForm
from schemas.seller import SellerCreate, SellerResponse
from services import auth_service

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post(
    "/register",
    response_model=SellerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация продавца",
)
async def register(
    data: SellerCreate,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.register(db, data)


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.login(db, data.username, data.password)


@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Обновить токены",
)
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.refresh_tokens(db, data.refresh_token)


@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выход",
)
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    await auth_service.logout(db, data.refresh_token)
