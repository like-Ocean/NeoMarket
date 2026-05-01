from pydantic import BaseModel, field_validator
from uuid import UUID


class InventoryItem(BaseModel):
    sku_id: UUID
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Количество должно быть больше нуля")
        return v


class InventoryRequest(BaseModel):
    items: list[InventoryItem]

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Список позиций не может быть пустым")
        return v
