"""Tdarr eligibility columns — now included in 0001, this migration is a no-op.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-15
"""

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass  # columns were added directly to 0001


def downgrade() -> None:
    pass
