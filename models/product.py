import uuid
import enum
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from models.seller import Seller
    from models.category import Category
    from models.sku import SKU
    from models.product_characteristic import ProductCharacteristic
    from models.product_image import ProductImage


class ProductStatus(str, enum.Enum):
    CREATED = "CREATED"
    ON_MODERATION = "ON_MODERATION"
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sellers.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus), nullable=False, default=ProductStatus.CREATED, index=True
    )
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocking_reason_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    moderator_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    seller: Mapped["Seller"] = relationship(back_populates="products")
    category: Mapped["Category"] = relationship(back_populates="products")
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    characteristics: Mapped[list["ProductCharacteristic"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    skus: Mapped[list["SKU"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

