from pydantic import BaseModel, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime
from models.invoice import InvoiceStatus


# Items

class InvoiceItemCreate(BaseModel):
    sku_id: UUID
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Количество должно быть больше нуля")
        return v


class InvoiceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku_id: UUID
    quantity: int
    accepted_quantity: int


# Invoice

class InvoiceCreate(BaseModel):
    items: list[InvoiceItemCreate]

    @field_validator("items")
    @classmethod
    def items_must_not_be_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Накладная должна содержать хотя бы одну позицию")
        return v


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    status: InvoiceStatus
    items: list[InvoiceItemResponse]
    created_at: datetime
    updated_at: datetime
    accepted_at: datetime | None = None
    accepted_by: UUID | None = None


class InvoicePaginatedResponse(BaseModel):
    items: list[InvoiceResponse]
    total_count: int
    limit: int
    offset: int


class InvoiceAcceptItem(BaseModel):
    invoice_item_id: UUID
    accepted_quantity: int


class InvoiceAcceptRequest(BaseModel):
    accepted_items: list[InvoiceAcceptItem] | None = None
