from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID
from datetime import datetime
from pydantic_extra_types.phone_numbers import PhoneNumber


class SellerCreate(BaseModel):
    email: EmailStr
    password: str
    company_name: str
    phone: PhoneNumber | None = None


class SellerUpdate(BaseModel):
    company_name: str | None = None
    phone: str | None = None


class SellerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    company_name: str
    phone: str | None
    created_at: datetime
    updated_at: datetime
