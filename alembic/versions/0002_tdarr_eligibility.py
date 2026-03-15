"""Add tdarr_eligible and tdarr_status to media_items

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_items",
        sa.Column("tdarr_eligible", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "media_items",
        sa.Column("tdarr_status", sa.String(30), nullable=True),
    )
    op.create_index("idx_media_items_tdarr_eligible", "media_items", ["tdarr_eligible"])


def downgrade() -> None:
    op.drop_index("idx_media_items_tdarr_eligible", "media_items")
    op.drop_column("media_items", "tdarr_status")
    op.drop_column("media_items", "tdarr_eligible")
