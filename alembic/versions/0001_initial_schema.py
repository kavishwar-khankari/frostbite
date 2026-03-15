"""Initial schema + item_playback_stats materialized view

Revision ID: 0001
Revises:
Create Date: 2026-03-15
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables are created by SQLAlchemy metadata (run via autogenerate or Base.metadata.create_all).
    # This migration adds only objects that SQLAlchemy cannot express: the materialized view.
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS item_playback_stats AS
        SELECT
            pe.media_item_id,
            COUNT(DISTINCT pe.user_id)                                              AS unique_viewers,
            COUNT(*) FILTER (WHERE pe.event_type = 'start')                        AS total_plays,
            MAX(pe.created_at) FILTER (WHERE pe.event_type = 'start')              AS last_played_at,
            COUNT(*) FILTER (
                WHERE pe.event_type = 'start'
                  AND pe.created_at > NOW() - INTERVAL '7 days'
            )                                                                       AS plays_last_7d,
            COUNT(*) FILTER (
                WHERE pe.event_type = 'start'
                  AND pe.created_at > NOW() - INTERVAL '30 days'
            )                                                                       AS plays_last_30d
        FROM playback_events pe
        GROUP BY pe.media_item_id
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_item_playback_stats_id "
        "ON item_playback_stats(media_item_id)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS item_playback_stats")
