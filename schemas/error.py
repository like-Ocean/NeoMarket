from pydantic import BaseModel
from typing import Optional


class ErrorResponse(BaseModel):
    """Единый формат ответа с ошибкой."""

    code: str
    message: str
    details: Optional[dict] = None

    class Config:
        json_schema_extra = {
            "example": {
                "code": "VALIDATION_ERROR",
                "message": "Поле 'title' обязательно",
                "details": {"additionalProp1": {}},
            }
        }
