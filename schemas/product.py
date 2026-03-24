from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from models.product import ProductStatus
from schemas.sku import SKUShortResponse


# Images

class ProductImageCreate(BaseModel):
    url: str
    ordering: int = 0


class ProductImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    ordering: int


# Characteristics

class ProductCharacteristicCreate(BaseModel):
    name: str
    value: str


class ProductCharacteristicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    value: str


# Product

class ProductCreate(BaseModel):
    category_id: UUID
    title: str
    description: str | None = None
    images: list[ProductImageCreate] = []
    characteristics: list[ProductCharacteristicCreate] = []


class ProductUpdate(BaseModel):
    category_id: UUID | None = None
    title: str | None = None
    description: str | None = None
    status: ProductStatus | None = None


class ProductShortResponse(BaseModel):
    # версия для списков
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: ProductStatus
    category_id: UUID
    created_at: datetime


class ProductResponse(BaseModel):
    # Полная версия — для детальной страницы
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    description: str | None
    status: ProductStatus
    images: list[ProductImageResponse]
    characteristics: list[ProductCharacteristicResponse]
    skus: list[SKUShortResponse]
    created_at: datetime
    updated_at: datetime


# Paginated

class ProductListResponse(BaseModel):
    total: int
    items: list[ProductShortResponse]
