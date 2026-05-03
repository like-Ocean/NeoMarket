import json
import uuid
from datetime import datetime
from sqlalchemy import select
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


async def fetch_pending_events(
    db: AsyncSession, batch_size: int,
    now: datetime, max_retries: int
) -> list[OutboxEvent]:
    result = await db.execute(
        select(OutboxEvent)
        .where(OutboxEvent.status == "PENDING")
        .where(OutboxEvent.retry_count < max_retries)
        .where(
            (OutboxEvent.next_retry_at.is_(None))
            | (OutboxEvent.next_retry_at <= now)
        )
        .order_by(OutboxEvent.created_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


def mark_sent(event: OutboxEvent, sent_at: datetime) -> None:
    event.status = "SENT"
    event.sent_at = sent_at
    event.next_retry_at = None


def schedule_retry(event: OutboxEvent, next_retry_at: datetime) -> None:
    event.retry_count += 1
    event.next_retry_at = next_retry_at
    event.status = "PENDING"


def mark_failed(event: OutboxEvent) -> None:
    event.status = "FAILED"