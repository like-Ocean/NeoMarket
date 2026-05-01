from pydantic import BaseModel, field_validator
from uuid import UUID


class ProductEventRequest(BaseModel):
    idempotency_key: str
    product_id: UUID
    event_type: str
    moderator_comment: str | None = None
    blocking_reason_id: UUID | None = None

    @field_validator("idempotency_key")
    @classmethod
    def idempotency_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("idempotency_key обязателен")
        return v.strip()

    @field_validator("event_type")
    @classmethod
    def event_type_required(cls, v: str) -> str:
        normalized = v.strip().upper()
        if normalized not in {"MODERATED", "BLOCKED", "HARD_BLOCKED"}:
            raise ValueError("event_type должен быть MODERATED, BLOCKED или HARD_BLOCKED")
        return normalized
