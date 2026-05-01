"""merge_heads

Revision ID: 99ab38f05fad
Revises: 5f8cf9e3f6c1, 9a1f0b2c3d4e
Create Date: 2026-05-02 02:17:08.457036

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99ab38f05fad'
down_revision: Union[str, Sequence[str], None] = ('5f8cf9e3f6c1', '9a1f0b2c3d4e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
