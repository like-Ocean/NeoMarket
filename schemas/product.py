from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from models.product import ProductStatus
from schemas.sku import SKUPublicResponse, SKUResponse


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

class Characteristic(BaseModel):
    name: str
    value: str


class CharacteristicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    value: str


# Product

class ProductCreate(BaseModel):
    category_id: UUID
    title: str
    slug: str | None = None
    description: str | None = None
    images: list[ProductImageCreate] = []
    characteristics: list[Characteristic] = []


class ProductUpdate(BaseModel):
    category_id: UUID | None = None
    title: str | None = None
    description: str | None = None
    characteristics: list[Characteristic] | None = None


class ProductShortResponse(BaseModel):
    # версия для списков
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    status: ProductStatus
    category_id: UUID
    deleted: bool
    created_at: datetime
    min_price: int | None = None
    cover_image: str | None = None


class ProductResponse(BaseModel):
    # Полная версия — для детальной страницы
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str
    description: str
    status: ProductStatus
    deleted: bool
    blocking_reason_id: UUID | None
    moderator_comment: str | None
    images: list[ProductImageResponse]
    characteristics: list[CharacteristicResponse]
    skus: list[SKUResponse]
    created_at: datetime
    updated_at: datetime


# Paginated

class ProductPaginatedResponse(BaseModel):
    items: list[ProductShortResponse]
    total_count: int
    limit: int
    offset: int


class ProductPublicShortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    status: ProductStatus
    category_id: UUID
    min_price: int
    cover_image: str | None = None
    created_at: datetime


class ProductPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str
    description: str
    status: ProductStatus
    images: list[ProductImageResponse]
    characteristics: list[CharacteristicResponse]
    skus: list[SKUPublicResponse]
    created_at: datetime
    updated_at: datetime


class ProductPublicPaginatedResponse(BaseModel):
    items: list[ProductPublicShortResponse]
    total_count: int
    limit: int
    offset: int


class ProductBatchRequest(BaseModel):
    product_ids: list[UUID]
