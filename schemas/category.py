from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime


class CategoryCreate(BaseModel):
    name: str
    parent_id: UUID | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None
    is_active: bool | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    parent_id: UUID | None
    level: int
    path: str
    is_active: bool
    created_at: datetime


class CategoryTreeResponse(BaseModel):
    id: UUID
    name: str
    children: list["CategoryTreeResponse"] = []



class CategoryWithChildrenResponse(CategoryResponse):
    children: list["CategoryResponse"] = []
