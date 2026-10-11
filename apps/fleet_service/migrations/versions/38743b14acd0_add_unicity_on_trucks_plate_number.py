"""Add unicity on trucks plate_number

Revision ID: 38743b14acd0
Revises: a228aa9dbfc9
Create Date: 2026-09-05 17:57:16.830911

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38743b14acd0'
down_revision: Union[str, Sequence[str], None] = 'a228aa9dbfc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint('trucks_plate_number_key', 'trucks', ['plate_number'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('trucks_plate_number_key', 'trucks', type_='unique')
