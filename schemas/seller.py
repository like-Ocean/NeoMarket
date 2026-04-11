from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime
from pydantic_extra_types.phone_numbers import PhoneNumber


class SellerCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    middle_name: str | None = None
    company_name: str
    phone: PhoneNumber | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_required_name_parts(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Имя и фамилия не могут быть пустыми")
        return normalized

    @field_validator("middle_name")
    @classmethod
    def validate_middle_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized


class SellerUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    company_name: str | None = None
    phone: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_optional_required_name_parts(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Имя и фамилия не могут быть пустыми")
        return normalized

    @field_validator("middle_name")
    @classmethod
    def validate_optional_middle_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized


class SellerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    first_name: str
    last_name: str
    middle_name: str | None
    company_name: str
    phone: str | None
    created_at: datetime
    updated_at: datetime
