"""Add upload_blocked flag to media_items for files with names too long for cloud storage.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_MAX_CLOUD_FILENAME = 120


def upgrade() -> None:
    op.add_column("media_items", sa.Column("upload_blocked", sa.Boolean, nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("media_items", "upload_blocked")
