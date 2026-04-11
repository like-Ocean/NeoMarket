from pydantic import BaseModel


class ProductImageCreateRequest(BaseModel):
    url: str
    ordering: int = 0


class ProductImageUpdateRequest(BaseModel):
    url: str | None = None
    ordering: int | None = None
