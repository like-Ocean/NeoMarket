from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime


class InventoryItem(BaseModel):
    sku_id: UUID
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Количество должно быть больше нуля")
        return v


class ReserveRequest(BaseModel):
    idempotency_key: UUID
    order_id: UUID
    items: list[InventoryItem]

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Список позиций не может быть пустым")
        return v


class ReserveResponse(BaseModel):
    order_id: UUID
    status: str
    reserved_at: datetime


class InventoryOrderRequest(BaseModel):
    order_id: UUID
    items: list[InventoryItem]

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Список позиций не может быть пустым")
        return v


class InventoryOrderResponse(BaseModel):
    order_id: UUID
    status: str
    processed_at: datetime
