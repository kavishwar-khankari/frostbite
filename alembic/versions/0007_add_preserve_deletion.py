"""Add deletion_candidates, deletion_exceptions tables and media_items.deleted_at.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_items",
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "deletion_exceptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("jellyfin_id", sa.String(64), nullable=True),
        sa.Column("series_id", sa.String(64), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_deletion_exceptions_scope", "deletion_exceptions", ["scope"])
    op.create_index("idx_deletion_exceptions_jellyfin_id", "deletion_exceptions", ["jellyfin_id"])
    op.create_index("idx_deletion_exceptions_series_id", "deletion_exceptions", ["series_id"])
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_deletion_exceptions_item "
        "ON deletion_exceptions (jellyfin_id) WHERE scope = 'item' AND jellyfin_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_deletion_exceptions_series "
        "ON deletion_exceptions (series_id) WHERE scope = 'series' AND series_id IS NOT NULL"
    )

    op.create_table(
        "deletion_candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("media_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("jellyfin_id", sa.String(64), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("series_id", sa.String(64), nullable=True),
        sa.Column("series_name", sa.Text, nullable=True),
        sa.Column("season_number", sa.Integer, nullable=True),
        sa.Column("episode_number", sa.Integer, nullable=True),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("temperature", sa.Float, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("notified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_deletion_candidates_status", "deletion_candidates", ["status"])
    op.create_index("idx_deletion_candidates_jellyfin_id", "deletion_candidates", ["jellyfin_id"])
    op.create_index("idx_deletion_candidates_media_item_id", "deletion_candidates", ["media_item_id"])
    op.create_index("idx_deletion_candidates_created_at", "deletion_candidates", ["created_at"])
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_deletion_candidates_active "
        "ON deletion_candidates (jellyfin_id) "
        "WHERE status IN ('pending', 'failed', 'deleted', 'protected')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_deletion_candidates_active")
    op.drop_index("idx_deletion_candidates_created_at", table_name="deletion_candidates")
    op.drop_index("idx_deletion_candidates_media_item_id", table_name="deletion_candidates")
    op.drop_index("idx_deletion_candidates_jellyfin_id", table_name="deletion_candidates")
    op.drop_index("idx_deletion_candidates_status", table_name="deletion_candidates")
    op.drop_table("deletion_candidates")

    op.execute("DROP INDEX IF EXISTS uq_deletion_exceptions_series")
    op.execute("DROP INDEX IF EXISTS uq_deletion_exceptions_item")
    op.drop_index("idx_deletion_exceptions_series_id", table_name="deletion_exceptions")
    op.drop_index("idx_deletion_exceptions_jellyfin_id", table_name="deletion_exceptions")
    op.drop_index("idx_deletion_exceptions_scope", table_name="deletion_exceptions")
    op.drop_table("deletion_exceptions")

    op.drop_column("media_items", "deleted_at")
