from pydantic import BaseModel, field_validator
from uuid import UUID


class FieldReport(BaseModel):
    field_name: str
    sku_id: UUID | None = None
    comment: str


class ModerationEventRequest(BaseModel):
    idempotency_key: UUID
    product_id: UUID
    event_type: str
    moderator_id: UUID | None = None
    moderator_comment: str | None = None
    blocking_reason_id: UUID | None = None
    hard_block: bool = False
    field_reports: list[FieldReport] | None = None
    occurred_at: str

    @field_validator("event_type")
    @classmethod
    def event_type_required(cls, v: str) -> str:
        normalized = v.strip().upper()
        if normalized not in {"MODERATED", "BLOCKED"}:
            raise ValueError("event_type должен быть MODERATED или BLOCKED")
        return normalized
