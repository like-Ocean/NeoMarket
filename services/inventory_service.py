import json
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from models.processed_event import ProcessedEvent
from models.sku import SKU
from services import outbox_service
from core.config import settings


async def reserve(db: AsyncSession, idempotency_key: UUID, items: list[tuple]) -> dict:
    existing_result = await db.execute(
        select(ProcessedEvent).where(
            ProcessedEvent.sender_service == "inventory",
            ProcessedEvent.idempotency_key == idempotency_key,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        try:
            payload = json.loads(existing.response_cached or "{}")
            response_payload = payload.get("response")
            if response_payload:
                return response_payload
        except json.JSONDecodeError:
            pass
        return {"reserved": True, "items": []}

    failed_items: list[dict] = []
    sku_by_id: dict[UUID, SKU] = {}

    for sku_id, qty in items:
        result = await db.execute(
            select(SKU).where(SKU.id == sku_id).with_for_update()
        )
        sku = result.scalar_one_or_none()
        if not sku:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {sku_id} не найден",
            )
        if sku.active_quantity < qty:
            failed_items.append({
                "sku_id": str(sku_id),
                "requested": qty,
                "available": sku.active_quantity,
                "reason": "INSUFFICIENT_STOCK",
            })
        sku_by_id[sku_id] = sku

    if failed_items:
        await db.rollback()
        return {"reserved": False, "failed_items": failed_items}

    response_items: list[dict] = []
    for sku_id, qty in items:
        sku = sku_by_id[sku_id]
        sku.active_quantity -= qty
        sku.reserved_quantity += qty
        response_items.append({
            "sku_id": str(sku_id),
            "reserved_quantity": qty,
            "remaining_stock": sku.active_quantity,
        })

        if sku.active_quantity == 0:
            await outbox_service.add_outbox_event(
                db,
                event_type="SKU_OUT_OF_STOCK",
                target_url=settings.B2C_SERVICE_URL,
                payload={
                    "event": "SKU_OUT_OF_STOCK",
                    "product_id": str(sku.product_id),
                    "sku_ids": [str(sku.id)],
                    "date": datetime.now(timezone.utc).isoformat(),
                },
            )

    response_payload = {"reserved": True, "items": response_items}
    db.add(ProcessedEvent(
        sender_service="inventory",
        idempotency_key=idempotency_key,
        response_cached=json.dumps(
            {
                "request": {
                    "idempotency_key": str(idempotency_key),
                    "items": [
                        {"sku_id": str(sku_id), "quantity": qty}
                        for sku_id, qty in items
                    ],
                },
                "response": response_payload,
            },
            ensure_ascii=False,
        ),
    ))

    await db.commit()
    return response_payload


async def unreserve(db: AsyncSession, order_id: UUID, items: list[tuple]) -> None:
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


async def fulfill(db: AsyncSession, order_id: UUID, items: list[tuple]) -> None:
    existing_result = await db.execute(
        select(ProcessedEvent).where(
            ProcessedEvent.sender_service == "inventory",
            ProcessedEvent.idempotency_key == order_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return

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

    db.add(ProcessedEvent(
        sender_service="inventory",
        idempotency_key=order_id,
        response_cached=json.dumps(
            {
                "order_id": str(order_id),
                "items": [
                    {"sku_id": str(sku_id), "quantity": qty}
                    for sku_id, qty in items
                ],
            },
            ensure_ascii=False,
        ),
    ))

    await db.commit()
