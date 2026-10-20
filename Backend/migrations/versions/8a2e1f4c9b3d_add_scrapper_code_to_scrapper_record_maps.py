"""add scrapper_code to scrapper_record_maps

Revision ID: 8a2e1f4c9b3d
Revises: 7764b56c7b34
Create Date: 2026-10-19 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a2e1f4c9b3d'
down_revision: Union[str, None] = '7764b56c7b34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scrapper_record_maps',
        sa.Column('scrapper_code', sa.String(length=50), nullable=True)
    )
    op.create_index(
        op.f('ix_scrapper_record_maps_scrapper_code'),
        'scrapper_record_maps',
        ['scrapper_code'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_scrapper_record_maps_scrapper_code'), table_name='scrapper_record_maps')
    op.drop_column('scrapper_record_maps', 'scrapper_code')
