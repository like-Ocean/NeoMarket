"""align models outbox processed events

Revision ID: b7c8d9e0f1a2
Revises: f8b3a5dd922c
Create Date: 2026-05-02 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "f8b3a5dd922c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop legacy stock reservations table and enum
    op.drop_index(op.f("ix_stock_reservations_status"), table_name="stock_reservations")
    op.drop_index(op.f("ix_stock_reservations_sku_id"), table_name="stock_reservations")
    op.drop_index(op.f("ix_stock_reservations_order_id"), table_name="stock_reservations")
    op.drop_table("stock_reservations")
    op.execute("DROP TYPE IF EXISTS reservation_status")

    # Sellers: add inn
    op.add_column("sellers", sa.Column("inn", sa.String(length=12), nullable=True))
    op.execute(
        "UPDATE sellers SET inn = right(replace(id::text, '-', ''), 12) WHERE inn IS NULL"
    )
    op.alter_column("sellers", "inn", nullable=False)
    op.create_unique_constraint("uq_sellers_inn", "sellers", ["inn"])

    # SKUs: add discount and image
    op.add_column(
        "skus",
        sa.Column("discount", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "skus",
        sa.Column("image", sa.String(length=1000), nullable=True),
    )
    op.create_check_constraint(
        "ck_skus_discount_non_negative",
        "skus",
        "discount >= 0",
    )
    op.alter_column("skus", "discount", server_default=None)

    # Products: add slug
    op.add_column(
        "products",
        sa.Column("slug", sa.String(length=255), nullable=True),
    )
    op.execute("UPDATE products SET slug = 'product-' || id::text WHERE slug IS NULL")
    op.alter_column("products", "slug", nullable=False)
    op.create_unique_constraint("uq_products_slug", "products", ["slug"])

    # Outbox events: align schema
    op.add_column(
        "outbox_events",
        sa.Column(
            "idempotency_key",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "target_url",
            sa.String(length=500),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "outbox_events",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_index(op.f("ix_outbox_events_aggregate_type"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_aggregate_id"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_sent"), table_name="outbox_events")
    op.drop_column("outbox_events", "aggregate_type")
    op.drop_column("outbox_events", "aggregate_id")
    op.drop_column("outbox_events", "sent")
    op.alter_column(
        "outbox_events",
        "id",
        server_default=sa.text("gen_random_uuid()"),
        existing_type=sa.UUID(),
    )
    op.create_unique_constraint(
        "uq_outbox_events_idempotency_key",
        "outbox_events",
        ["idempotency_key"],
    )
    op.alter_column("outbox_events", "idempotency_key", server_default=None)
    op.alter_column("outbox_events", "target_url", server_default=None)
    op.alter_column("outbox_events", "status", server_default=None)
    op.alter_column("outbox_events", "retry_count", server_default=None)

    # Processed events: rename and reshape inbox_events
    op.execute("DROP TABLE IF EXISTS processed_events CASCADE")
    
    # Create fresh processed_events table
    op.create_table(
        'processed_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('sender_service', sa.String(length=20), nullable=False),
        sa.Column('idempotency_key', sa.UUID(), nullable=False),
        sa.Column('response_cached', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sender_service', 'idempotency_key', name='uq_processed_events_sender_key')
    )
    op.create_index('ix_processed_events_idempotency_key', 'processed_events', ['idempotency_key'])


def downgrade() -> None:
    # Processed events: drop fresh table
    op.drop_index('ix_processed_events_idempotency_key', table_name='processed_events')
    op.drop_table('processed_events')

    # Outbox events: restore legacy schema
    op.drop_constraint(
        "uq_outbox_events_idempotency_key",
        "outbox_events",
        type_="unique",
    )
    op.drop_column("outbox_events", "next_retry_at")
    op.drop_column("outbox_events", "retry_count")
    op.drop_column("outbox_events", "status")
    op.drop_column("outbox_events", "target_url")
    op.drop_column("outbox_events", "idempotency_key")
    op.add_column(
        "outbox_events",
        sa.Column("aggregate_type", sa.String(length=50), nullable=False),
    )
    op.add_column(
        "outbox_events",
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
    )
    op.add_column(
        "outbox_events",
        sa.Column("sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        op.f("ix_outbox_events_aggregate_type"),
        "outbox_events",
        ["aggregate_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_aggregate_id"),
        "outbox_events",
        ["aggregate_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_sent"),
        "outbox_events",
        ["sent"],
        unique=False,
    )
    op.alter_column("outbox_events", "id", server_default=None, existing_type=sa.UUID())

    # Products: drop slug
    op.drop_constraint("uq_products_slug", "products", type_="unique")
    op.drop_column("products", "slug")

    # SKUs: drop discount and image
    op.drop_constraint("ck_skus_discount_non_negative", "skus", type_="check")
    op.drop_column("skus", "image")
    op.drop_column("skus", "discount")

    # Sellers: drop inn
    op.drop_constraint("uq_sellers_inn", "sellers", type_="unique")
    op.drop_column("sellers", "inn")

    # Restore stock_reservations
    reservation_status = sa.Enum(
        "RESERVED",
        "RELEASED",
        "COMMITTED",
        name="reservation_status",
    )
    reservation_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("sku_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", reservation_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stock_reservations_order_id"),
        "stock_reservations",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_reservations_sku_id"),
        "stock_reservations",
        ["sku_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_reservations_status"),
        "stock_reservations",
        ["status"],
        unique=False,
    )