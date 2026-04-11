"""add seller name parts

Revision ID: 5f8cf9e3f6c1
Revises: 2355ef707e36
Create Date: 2026-04-11 21:28:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5f8cf9e3f6c1"
down_revision: Union[str, Sequence[str], None] = "2355ef707e36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sellers",
        sa.Column("first_name", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column(
        "sellers",
        sa.Column("last_name", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column(
        "sellers",
        sa.Column("middle_name", sa.String(length=100), nullable=True),
    )

    op.alter_column("sellers", "first_name", server_default=None)
    op.alter_column("sellers", "last_name", server_default=None)


def downgrade() -> None:
    op.drop_column("sellers", "middle_name")
    op.drop_column("sellers", "last_name")
    op.drop_column("sellers", "first_name")
