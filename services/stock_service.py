from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.sku import SKU
from models.stock_reservation import StockReservation, ReservationStatus


async def reserve(db: AsyncSession, order_id: UUID, items: list[dict]) -> None:
    for item in items:
        sku_id = UUID(item["sku_id"])
        quantity = int(item["quantity"])

        result = await db.execute(select(SKU).where(SKU.id == sku_id))
        sku = result.scalar_one_or_none()

        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} не найден",
            )
        if sku.active_quantity < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Недостаточно товара для SKU {sku_id}. "
                       f"Доступно: {sku.active_quantity}, запрошено: {quantity}",
            )

        sku.active_quantity -= quantity
        sku.reserved_quantity += quantity

        db.add(StockReservation(
            order_id=order_id, sku_id=sku_id,
            quantity=quantity, status=ReservationStatus.RESERVED
        ))

    await db.commit()


async def release(db: AsyncSession, order_id: UUID) -> None:
    result = await db.execute(
        select(StockReservation).where(
            StockReservation.order_id == order_id,
            StockReservation.status == ReservationStatus.RESERVED,
        )
    )
    reservations = result.scalars().all()

    if not reservations:
        return

    for reservation in reservations:
        sku_result = await db.execute(select(SKU).where(SKU.id == reservation.sku_id))
        sku = sku_result.scalar_one_or_none()

        if sku:
            sku.active_quantity += reservation.quantity
            sku.reserved_quantity -= reservation.quantity

        reservation.status = ReservationStatus.RELEASED

    await db.commit()


async def commit(db: AsyncSession, order_id: UUID) -> None:
    result = await db.execute(
        select(StockReservation).where(
            StockReservation.order_id == order_id,
            StockReservation.status == ReservationStatus.RESERVED,
        )
    )
    reservations = result.scalars().all()

    if not reservations:
        return

    for reservation in reservations:
        sku_result = await db.execute(select(SKU).where(SKU.id == reservation.sku_id))
        sku = sku_result.scalar_one_or_none()

        if sku:
            sku.reserved_quantity -= reservation.quantity

        reservation.status = ReservationStatus.COMMITTED

    await db.commit()