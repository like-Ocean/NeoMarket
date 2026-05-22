"""add PARTIALLY_ACCEPTED and CANCELLED to invoicestatus

Revision ID: 40282a8c0bc6
Revises: 319219d0b078
Create Date: 2026-05-22 20:41:15.571730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40282a8c0bc6'
down_revision: Union[str, Sequence[str], None] = '319219d0b078'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE invoicestatus ADD VALUE 'PARTIALLY_ACCEPTED'")
    op.execute("ALTER TYPE invoicestatus ADD VALUE 'CANCELLED'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
