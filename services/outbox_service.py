import json
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from models.outbox_event import OutboxEvent


async def add_outbox_event(
    db: AsyncSession, event_type: str,
    target_url: str, payload: dict
):
    idempotency_key = uuid.uuid4()
    payload_with_key = {
        "idempotency_key": str(idempotency_key),
        **payload,
    }

    db.add(OutboxEvent(
        idempotency_key=idempotency_key,
        event_type=event_type,
        target_url=target_url,
        payload=json.dumps(payload_with_key, ensure_ascii=False),
    ))