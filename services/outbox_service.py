import json
import uuid
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from models.outbox_event import OutboxEvent


async def add_outbox_event(
    db: AsyncSession, event_type: str,
    aggregate_type: str, aggregate_id: UUID,
    payload: dict,
):
    db.add(OutboxEvent(
        idempotency_key=str(uuid.uuid4()),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=json.dumps(payload, ensure_ascii=False),
        sent=False
    ))