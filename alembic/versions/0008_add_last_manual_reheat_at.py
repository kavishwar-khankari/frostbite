"""Add last_manual_reheat_at to media_items for freeze hold after manual reheat.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_items", sa.Column("last_manual_reheat_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("media_items", "last_manual_reheat_at")
