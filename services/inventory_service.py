from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from models.sku import SKU


def _raise_insufficient(sku_id):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Недостаточно доступного остатка для SKU {sku_id}",
    )


async def reserve(db: AsyncSession, items: list[tuple]) -> None:
    for sku_id, qty in items:
        result = await db.execute(
            select(SKU).where(SKU.id == sku_id).with_for_update()
        )
        sku = result.scalar_one_or_none()
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} не найден",
            )
        if sku.active_quantity < qty:
            _raise_insufficient(sku_id)
        sku.active_quantity -= qty
        sku.reserved_quantity += qty

    await db.commit()


async def unreserve(db: AsyncSession, items: list[tuple]) -> None:
    for sku_id, qty in items:
        result = await db.execute(
            select(SKU).where(SKU.id == sku_id).with_for_update()
        )
        sku = result.scalar_one_or_none()
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} не найден",
            )
        if sku.reserved_quantity < qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Недостаточно зарезервированного остатка для SKU {sku_id}",
            )
        sku.reserved_quantity -= qty
        sku.active_quantity += qty

    await db.commit()


async def fulfill(db: AsyncSession, items: list[tuple]) -> None:
    for sku_id, qty in items:
        result = await db.execute(
            select(SKU).where(SKU.id == sku_id).with_for_update()
        )
        sku = result.scalar_one_or_none()
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} не найден",
            )
        if sku.reserved_quantity < qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Недостаточно зарезервированного остатка для SKU {sku_id}",
            )
        sku.reserved_quantity -= qty

    await db.commit()
