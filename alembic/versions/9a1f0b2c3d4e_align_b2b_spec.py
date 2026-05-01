"""align b2b spec

Revision ID: 9a1f0b2c3d4e
Revises: 2355ef707e36
Create Date: 2026-05-01 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a1f0b2c3d4e"
down_revision: Union[str, Sequence[str], None] = "2355ef707e36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE productstatus ADD VALUE IF NOT EXISTS 'HARD_BLOCKED'")

    op.add_column("products", sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("products", sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("products", sa.Column("blocking_reason_id", sa.UUID(), nullable=True))
    op.add_column("products", sa.Column("moderator_comment", sa.Text(), nullable=True))

    op.drop_constraint("products_seller_id_fkey", "products", type_="foreignkey")
    op.create_foreign_key(
        "products_seller_id_fkey",
        "products",
        "sellers",
        ["seller_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.alter_column("products", "title", type_=sa.String(length=255), existing_type=sa.String(length=500))
    op.execute("UPDATE products SET description = '' WHERE description IS NULL")
    op.alter_column("products", "description", nullable=False, server_default="")
    op.alter_column("products", "description", server_default=None)

    op.add_column("skus", sa.Column("cost_price", sa.BigInteger(), nullable=True))
    op.add_column("skus", sa.Column("active_quantity", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("skus", sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0"))

    op.execute("UPDATE skus SET active_quantity = stock_quantity, reserved_quantity = 0")

    op.drop_constraint("ck_skus_stock_non_negative", "skus", type_="check")
    op.create_check_constraint("ck_skus_active_non_negative", "skus", "active_quantity >= 0")
    op.create_check_constraint("ck_skus_reserved_non_negative", "skus", "reserved_quantity >= 0")

    op.drop_column("skus", "stock_quantity")

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_outbox_events_event_type"), "outbox_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_outbox_events_aggregate_type"), "outbox_events", ["aggregate_type"], unique=False)
    op.create_index(op.f("ix_outbox_events_aggregate_id"), "outbox_events", ["aggregate_id"], unique=False)
    op.create_index(op.f("ix_outbox_events_sent"), "outbox_events", ["sent"], unique=False)

    op.create_table(
        "inbox_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_inbox_events_idempotency_key"), "inbox_events", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_inbox_events_idempotency_key"), table_name="inbox_events")
    op.drop_table("inbox_events")

    op.drop_index(op.f("ix_outbox_events_sent"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_aggregate_id"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_aggregate_type"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_event_type"), table_name="outbox_events")
    op.drop_table("outbox_events")

    op.add_column("skus", sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"))
    op.drop_constraint("ck_skus_reserved_non_negative", "skus", type_="check")
    op.drop_constraint("ck_skus_active_non_negative", "skus", type_="check")
    op.create_check_constraint("ck_skus_stock_non_negative", "skus", "stock_quantity >= 0")
    op.drop_column("skus", "reserved_quantity")
    op.drop_column("skus", "active_quantity")
    op.drop_column("skus", "cost_price")

    op.alter_column("products", "description", nullable=True)
    op.alter_column("products", "title", type_=sa.String(length=500), existing_type=sa.String(length=255))
    op.drop_column("products", "moderator_comment")
    op.drop_column("products", "blocking_reason_id")
    op.drop_column("products", "blocked")
    op.drop_column("products", "deleted")
