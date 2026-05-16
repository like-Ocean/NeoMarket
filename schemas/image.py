from pydantic import BaseModel
from uuid import UUID


class ImageUploadRequest(BaseModel):
    entity_type: str
    entity_id: UUID | None = None
    ordering: int = 0


class ImageAttachRequest(BaseModel):
    image_id: UUID | None = None
    url: str | None = None
    ordering: int = 0


class ImageUpdateRequest(BaseModel):
    url: str | None = None
    ordering: int | None = None


class ImageUploadResponse(BaseModel):
    id: UUID
    url: str
    ordering: int
    entity_type: str
    entity_id: UUID | None
