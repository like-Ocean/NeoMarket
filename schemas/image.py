from pydantic import BaseModel
from uuid import UUID


class ProductImageCreateRequest(BaseModel):
    url: str
    ordering: int = 0


class ProductImageUpdateRequest(BaseModel):
    url: str | None = None
    ordering: int | None = None


class ImageUploadResponse(BaseModel):
    id: UUID
    url: str
    ordering: int
    entity_type: str
    entity_id: UUID
