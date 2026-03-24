from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime


class CategoryCreate(BaseModel):
    name: str
    parent_id: UUID | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    parent_id: UUID | None
    created_at: datetime


class CategoryWithChildrenResponse(CategoryResponse):
    children: list["CategoryResponse"] = []
