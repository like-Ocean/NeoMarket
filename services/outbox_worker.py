import asyncio
import json
import logging
import random
from datetime import datetime, timezone, timedelta
import httpx
from core.config import settings
from core.database import AsyncSessionLocal
from services.outbox_service import (
    fetch_pending_events, mark_failed,
    mark_sent, schedule_retry
)

logger = logging.getLogger(__name__)


def _get_service_key(target_url: str) -> str | None:
    if settings.MODERATION_SERVICE_URL and target_url.startswith(settings.MODERATION_SERVICE_URL):
        return settings.B2B_TO_MOD_KEY or None
    if settings.B2C_SERVICE_URL and target_url.startswith(settings.B2C_SERVICE_URL):
        return settings.B2B_TO_B2C_KEY or None
    return None


def _next_retry_time(retry_count: int) -> datetime:
    base_delay = settings.OUTBOX_BASE_BACKOFF_SECONDS
    max_delay = settings.OUTBOX_MAX_BACKOFF_SECONDS
    delay = min(max_delay, base_delay * (2 ** (retry_count - 1)))
    jitter = random.uniform(0, delay * 0.1)
    return datetime.now(timezone.utc) + timedelta(seconds=delay + jitter)


async def _send_event(client: httpx.AsyncClient, event) -> tuple[bool, bool]:
    try:
        payload = json.loads(event.payload)
    except json.JSONDecodeError:
        logger.warning("Invalid outbox payload JSON for event %s", event.id)
        return False, True

    headers: dict[str, str] = {"Content-Type": "application/json"}
    service_key = _get_service_key(event.target_url)
    if service_key:
        headers["X-Service-Key"] = service_key

    try:
        response = await client.post(
            event.target_url,
            json=payload,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.warning("Outbox delivery error for event %s: %s", event.id, exc)
        return False, False

    if 200 <= response.status_code < 300:
        return True, False
    if response.status_code == 429:
        return False, False
    if 400 <= response.status_code < 500:
        logger.warning(
            "Outbox event %s failed with status %s", event.id, response.status_code
        )
        return False, True

    logger.warning(
        "Outbox event %s retryable status %s", event.id, response.status_code
    )
    return False, False


async def run_outbox_worker(stop_event: asyncio.Event) -> None:
    timeout = httpx.Timeout(settings.OUTBOX_HTTP_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while not stop_event.is_set():
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                events = await fetch_pending_events(
                    db,
                    settings.OUTBOX_BATCH_SIZE,
                    now,
                    settings.OUTBOX_MAX_RETRIES,
                )

                for event in events:
                    success, permanent_failure = await _send_event(client, event)
                    if success:
                        mark_sent(event, datetime.now(timezone.utc))
                        continue

                    if permanent_failure:
                        mark_failed(event)
                        continue

                    next_attempt = event.retry_count + 1
                    if next_attempt >= settings.OUTBOX_MAX_RETRIES:
                        mark_failed(event)
                        continue

                    schedule_retry(event, _next_retry_time(next_attempt))

                await db.commit()

            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.OUTBOX_POLL_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                continue
