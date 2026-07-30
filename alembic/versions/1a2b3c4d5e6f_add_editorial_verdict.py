"""add editorial_verdict to products

Revision ID: 1a2b3c4d5e6f
Revises: aa30b544ed16
Create Date: 2026-07-30 23:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "aa30b544ed16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("editorial_verdict", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "editorial_verdict")
