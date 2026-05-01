import uuid
import enum
from typing import TYPE_CHECKING
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from models.sku import SKU


class ReservationStatus(str, enum.Enum):
    RESERVED = "reserved"
    RELEASED = "released"
    COMMITTED = "committed"


class StockReservation(Base, TimestampMixin):
    __tablename__ = "stock_reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        SAEnum(ReservationStatus, name="reservation_status"),
        nullable=False,
        default=ReservationStatus.RESERVED, index=True
    )

    # Relationships
    sku: Mapped["SKU"] = relationship(back_populates="reservations")