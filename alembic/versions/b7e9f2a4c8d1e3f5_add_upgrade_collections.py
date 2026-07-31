"""add upgrade collections (Pimp My Ride layer)

Revision ID: b7e9f2a4c8d1e3f5
Revises: aa612bf56e9d
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e9f2a4c8d1e3f5'
down_revision: Union[str, Sequence[str], None] = 'aa612bf56e9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('upgrade_collections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('slug', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('icon', sa.String(length=100), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_upgrade_collections_slug'), 'upgrade_collections', ['slug'], unique=True)
    op.create_table('product_upgrade_collections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('upgrade_collection_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['upgrade_collection_id'], ['upgrade_collections.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product_id', 'upgrade_collection_id', name='uq_product_upgrade_collection')
    )
    op.create_index('ix_product_upgrade_collections_collection', 'product_upgrade_collections', ['upgrade_collection_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_product_upgrade_collections_collection', table_name='product_upgrade_collections')
    op.drop_table('product_upgrade_collections')
    op.drop_index(op.f('ix_upgrade_collections_slug'), table_name='upgrade_collections')
    op.drop_table('upgrade_collections')
