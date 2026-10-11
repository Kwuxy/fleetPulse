"""rename requested_date to requested_datetime

Revision ID: 04809a5c8def
Revises: 2083285b7227
Create Date: 2026-10-11 15:18:06.333002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '04809a5c8def'
down_revision: Union[str, Sequence[str], None] = '2083285b7227'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('deliveries', 'requested_date', new_column_name='requested_datetime',
                    type_=sa.DateTime(timezone=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('deliveries', 'requested_datetime', new_column_name='requested_date', type_=sa.Date())
