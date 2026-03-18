"""Add last_prefetch_at to media_items for prefetch cooldown.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_items", sa.Column("last_prefetch_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("media_items", "last_prefetch_at")
