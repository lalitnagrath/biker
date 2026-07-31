"""add motorcycle hero_image/description and collection fields

Revision ID: aa612bf56e9d
Revises: 1a2b3c4d5e6f
Create Date: 2026-07-31 10:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa612bf56e9d'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('motorcycles', sa.Column('hero_image', sa.String(length=1024), nullable=True))
    op.add_column('motorcycles', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('collections', sa.Column('hero_image', sa.String(length=1024), nullable=True))
    op.add_column('collections', sa.Column('seo_title', sa.String(length=255), nullable=True))
    op.add_column('collections', sa.Column('seo_description', sa.Text(), nullable=True))
    op.add_column('collections', sa.Column('is_featured', sa.Boolean(), nullable=True))
    op.add_column('collections', sa.Column('rule_type', sa.String(length=20), nullable=True))
    op.add_column('collections', sa.Column('rule_definition', sa.JSON(), nullable=True))
    op.add_column('collection_items', sa.Column('is_featured', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('collection_items', 'is_featured')
    op.drop_column('collections', 'rule_definition')
    op.drop_column('collections', 'rule_type')
    op.drop_column('collections', 'is_featured')
    op.drop_column('collections', 'seo_description')
    op.drop_column('collections', 'seo_title')
    op.drop_column('collections', 'hero_image')
    op.drop_column('motorcycles', 'description')
    op.drop_column('motorcycles', 'hero_image')
