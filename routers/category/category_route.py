from uuid import UUID
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_seller
from schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryWithChildrenResponse
from services import category_service

category_router = APIRouter(prefix="/categories", tags=["Categories"])


@category_router.get(
    "",
    response_model=list[CategoryResponse],
    summary="Список категорий",
)
async def get_categories(
    parent_id: UUID | None = None, only_root: bool = False,
    db: AsyncSession = Depends(get_db),
):
    return await category_service.get_categories(db, parent_id, only_root)


@category_router.get(
    "/{category_id}",
    response_model=CategoryWithChildrenResponse,
    summary="Категория с подкатегориями",
)
async def get_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    category = await category_service.get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        )
    return category


@category_router.post(
    "",
    response_model=CategoryWithChildrenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать категорию",
)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_seller),
):
    return await category_service.create_category(db, data)


@category_router.patch(
    "/{category_id}",
    response_model=CategoryWithChildrenResponse,
    summary="Обновить категорию",
)
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_seller),
):
    category = await category_service.get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        )
    return await category_service.update_category(db, category, data)


@category_router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить категорию",
)
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_seller),
):
    category = await category_service.get_category_by_id(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        )
    await category_service.delete_category(db, category)

