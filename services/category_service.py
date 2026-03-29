from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from models.category import Category
from models.product import Product
from schemas.category import CategoryCreate, CategoryUpdate


async def get_category_by_id(db: AsyncSession, category_id) -> Category | None:
    result = await db.execute(
        select(Category)
        .options(selectinload(Category.children))
        .where(Category.id == category_id)
    )
    return result.scalar_one_or_none()


async def get_categories(db: AsyncSession, parent_id=None, only_root: bool = False) -> list[Category]:
    query = select(Category).options(selectinload(Category.children))
    if only_root:
        query = query.where(Category.parent_id == None)
    elif parent_id is not None:
        query = query.where(Category.parent_id == parent_id)

    result = await db.execute(query)
    return result.scalars().all()


async def create_category(db: AsyncSession, data: CategoryCreate) -> Category:
    if data.parent_id:
        parent = await get_category_by_id(db, data.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Родительская категория не найдена",
            )

    category = Category(
        name=data.name,
        parent_id=data.parent_id,
    )
    db.add(category)
    await db.commit()

    return await get_category_by_id(db, category.id)


async def update_category(db: AsyncSession, category: Category, data: CategoryUpdate) -> Category:
    if data.parent_id:
        if data.parent_id == category.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Категория не может быть родителем самой себя",
            )
        parent = await get_category_by_id(db, data.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Родительская категория не найдена",
            )

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)

    await db.commit()

    return await get_category_by_id(db, category.id)


async def delete_category(db: AsyncSession, category: Category):
    product_result = await db.execute(
        select(Product.id)
        .where(Product.category_id == category.id)
        .limit(1)
    )
    has_products = product_result.scalar_one_or_none()
    if has_products:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Категория содержит товары и не может быть удалена",
        )

    await db.delete(category)
    await db.commit()
