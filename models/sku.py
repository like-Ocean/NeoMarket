import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, BigInteger, Integer, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from models.product import Product
    from models.sku_image import SKUImage
    from models.sku_characteristic import SKUCharacteristic
    from models.invoice import InvoiceItem


class SKU(Base, TimestampMixin):
    __tablename__ = "skus"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_skus_price_non_negative"),
        CheckConstraint("stock_quantity >= 0", name="ck_skus_stock_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    article: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="skus")
    images: Mapped[list["SKUImage"]] = relationship(
        back_populates="sku", cascade="all, delete-orphan"
    )
    characteristics: Mapped[list["SKUCharacteristic"]] = relationship(
        back_populates="sku", cascade="all, delete-orphan"
    )
    invoice_items: Mapped[list["InvoiceItem"]] = relationship(back_populates="sku")



