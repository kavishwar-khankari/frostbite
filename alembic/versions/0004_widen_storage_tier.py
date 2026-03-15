"""Widen storage_tier and transfer_direction columns from VARCHAR(10) to VARCHAR(20).

'transferring' is 11 chars and was overflowing VARCHAR(10).

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "media_items", "storage_tier",
        type_=sa.String(20),
        existing_type=sa.String(10),
        existing_nullable=False,
    )
    op.alter_column(
        "media_items", "transfer_direction",
        type_=sa.String(20),
        existing_type=sa.String(10),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "media_items", "storage_tier",
        type_=sa.String(10),
        existing_type=sa.String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "media_items", "transfer_direction",
        type_=sa.String(10),
        existing_type=sa.String(20),
        existing_nullable=True,
    )
