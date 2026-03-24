import uuid
import enum
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from models.seller import Seller
    from models.invoice_item import InvoiceItem


class InvoiceStatus(str, enum.Enum):
    CREATED = "CREATED"
    ACCEPTED = "ACCEPTED"


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sellers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus), nullable=False, default=InvoiceStatus.CREATED
    )

    # Relationships
    seller: Mapped["Seller"] = relationship(back_populates="invoices")
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


