import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from core.database import TimestampMixin, Base

if TYPE_CHECKING:
    from models.product import Product
    from models.invoice import Invoice
    from models.refresh_token import RefreshToken


class Seller(Base, TimestampMixin):
    __tablename__ = "sellers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(500), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    products: Mapped[list["Product"]] = relationship(back_populates="seller")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="seller")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="seller", cascade="all, delete-orphan"
    )
