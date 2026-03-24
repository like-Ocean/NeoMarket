from pydantic import BaseModel, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime


# Images

class SKUImageCreate(BaseModel):
    url: str
    ordering: int = 0


class SKUImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    ordering: int


# Characteristics

class SKUCharacteristicCreate(BaseModel):
    name: str
    value: str


class SKUCharacteristicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    value: str


# SKU

class SKUCreate(BaseModel):
    product_id: UUID
    name: str
    price: int
    stock_quantity: int = 0
    article: str | None = None
    images: list[SKUImageCreate] = []
    characteristics: list[SKUCharacteristicCreate] = []

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Цена не может быть отрицательной")
        return v

    @field_validator("stock_quantity")
    @classmethod
    def stock_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Остаток не может быть отрицательным")
        return v


class SKUUpdate(BaseModel):
    name: str | None = None
    price: int | None = None
    article: str | None = None

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("Цена не может быть отрицательной")
        return v


class SKUResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    name: str
    price: int
    stock_quantity: int
    article: str | None
    images: list[SKUImageResponse]
    characteristics: list[SKUCharacteristicResponse]
    created_at: datetime
    updated_at: datetime


class SKUShortResponse(BaseModel):
    # версия — используется внутри ProductResponse
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price: int
    stock_quantity: int
    article: str | None
