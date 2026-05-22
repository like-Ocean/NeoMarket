import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from models.processed_event import ProcessedEvent
from models.product import Product, ProductStatus
from models.sku import SKU
from schemas.events import ModerationEventRequest
from services.outbox_service import add_outbox_event
from core.config import settings


async def handle_moderation_event(db: AsyncSession, data: ModerationEventRequest) -> None:
    result = await db.execute(
        select(ProcessedEvent).where(
            ProcessedEvent.sender_service == "moderation",
            ProcessedEvent.idempotency_key == data.idempotency_key,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return

    product_result = await db.execute(
        select(Product).where(Product.id == data.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "Товар не найден"},
        )

    if data.event_type == "MODERATED":
        product.status = ProductStatus.MODERATED
        product.blocked = False
        product.moderator_comment = data.moderator_comment
        product.blocking_reason_id = None
    elif data.event_type == "BLOCKED":
        product.status = (
            ProductStatus.HARD_BLOCKED if data.hard_block else ProductStatus.BLOCKED
        )
        product.blocked = True
        product.moderator_comment = data.moderator_comment
        product.blocking_reason_id = data.blocking_reason_id

        sku_result = await db.execute(
            select(SKU.id).where(SKU.product_id == product.id)
        )
        sku_ids = [str(sku_id) for sku_id in sku_result.scalars().all()]

        await add_outbox_event(
            db=db,
            event_type="PRODUCT_BLOCKED",
            target_url=settings.B2C_SERVICE_URL,
            payload={
                "event": "PRODUCT_BLOCKED",
                "product_id": str(product.id),
                "sku_ids": sku_ids,
                "date": datetime.now(timezone.utc).isoformat(),
            },
        )

    db.add(ProcessedEvent(
        sender_service="moderation",
        idempotency_key=data.idempotency_key,
        response_cached=json.dumps({"accepted": True}, ensure_ascii=False),
    ))

    await db.commit()
