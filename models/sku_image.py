import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base

if TYPE_CHECKING:
    from models.sku import SKU


class SKUImage(Base):
    __tablename__ = "sku_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sku: Mapped["SKU"] = relationship(back_populates="images")
