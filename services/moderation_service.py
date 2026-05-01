import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from models.inbox_event import InboxEvent
from models.product import Product, ProductStatus
from schemas.events import ProductEventRequest


async def handle_product_event(db: AsyncSession, data: ProductEventRequest) -> None:
    result = await db.execute(
        select(InboxEvent).where(InboxEvent.idempotency_key == data.idempotency_key)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return

    product_result = await db.execute(
        select(Product).where(Product.id == data.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")

    if data.event_type == "MODERATED":
        product.status = ProductStatus.MODERATED
        product.blocked = False
        product.moderator_comment = data.moderator_comment
        product.blocking_reason_id = None
    elif data.event_type == "BLOCKED":
        product.status = ProductStatus.BLOCKED
        product.blocked = True
        product.moderator_comment = data.moderator_comment
        product.blocking_reason_id = data.blocking_reason_id
    elif data.event_type == "HARD_BLOCKED":
        product.status = ProductStatus.HARD_BLOCKED
        product.blocked = True
        product.moderator_comment = data.moderator_comment
        product.blocking_reason_id = data.blocking_reason_id

    db.add(InboxEvent(
        idempotency_key=data.idempotency_key,
        event_type=data.event_type,
        aggregate_id=data.product_id,
        payload=json.dumps(data.model_dump(), ensure_ascii=False),
    ))

    await db.commit()
