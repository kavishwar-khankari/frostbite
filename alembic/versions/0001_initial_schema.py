"""Initial schema — all tables + item_playback_stats materialized view

Revision ID: 0001
Revises:
Create Date: 2026-03-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── media_items ───────────────────────────────────────────────────────────
    op.create_table(
        "media_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("jellyfin_id", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("series_id", sa.String(64), nullable=True),
        sa.Column("series_name", sa.Text, nullable=True),
        sa.Column("season_number", sa.Integer, nullable=True),
        sa.Column("episode_number", sa.Integer, nullable=True),
        # File info
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("codec", sa.String(20), nullable=True),
        sa.Column("resolution", sa.String(10), nullable=True),
        # Tdarr gate
        sa.Column("tdarr_eligible", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("tdarr_status", sa.String(30), nullable=True),
        # Storage state
        sa.Column("storage_tier", sa.String(10), nullable=False, server_default="hot"),
        sa.Column("transfer_direction", sa.String(10), nullable=True),
        # Scoring
        sa.Column("temperature", sa.Float, nullable=False, server_default="100.0"),
        sa.Column("last_scored_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # Jellyfin metadata
        sa.Column("date_added", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("premiere_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("community_rating", sa.Float, nullable=True),
        # Sonarr/Radarr metadata
        sa.Column("series_status", sa.String(20), nullable=True),
        sa.Column("monitored", sa.Boolean, server_default="true"),
        # Timestamps
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_media_items_jellyfin_id", "media_items", ["jellyfin_id"])
    op.create_index("idx_media_items_series_id", "media_items", ["series_id"])
    op.create_index("idx_media_items_temperature", "media_items", ["temperature"])
    op.create_index("idx_media_items_storage_tier", "media_items", ["storage_tier"])
    op.create_index("idx_media_items_tdarr_eligible", "media_items", ["tdarr_eligible"])

    # ── playback_events ───────────────────────────────────────────────────────
    op.create_table(
        "playback_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("media_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("username", sa.Text, nullable=True),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("play_method", sa.String(20), nullable=True),
        sa.Column("position_ticks", sa.BigInteger, nullable=True),
        sa.Column("duration_ticks", sa.BigInteger, nullable=True),
        sa.Column("client_name", sa.Text, nullable=True),
        sa.Column("device_name", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_playback_events_media_item", "playback_events",
                    ["media_item_id", "created_at"])
    op.create_index("idx_playback_events_created", "playback_events", ["created_at"])

    # ── transfers ─────────────────────────────────────────────────────────────
    op.create_table(
        "transfers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("media_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="50"),
        sa.Column("rclone_job_id", sa.Integer, nullable=True),
        sa.Column("rclone_group", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("bytes_transferred", sa.BigInteger, server_default="0"),
        sa.Column("bytes_total", sa.BigInteger, server_default="0"),
        sa.Column("speed_bps", sa.BigInteger, server_default="0"),
        sa.Column("eta_seconds", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("queued_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.Column("dest_path", sa.Text, nullable=False),
    )
    op.create_index("idx_transfers_status", "transfers", ["status"])
    op.create_index("idx_transfers_media_item", "transfers", ["media_item_id"])

    # ── score_history ─────────────────────────────────────────────────────────
    op.create_table(
        "score_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("total_items", sa.Integer, nullable=False),
        sa.Column("hot_items", sa.Integer, nullable=False),
        sa.Column("cold_items", sa.Integer, nullable=False),
        sa.Column("nas_used_bytes", sa.BigInteger, nullable=False),
        sa.Column("cloud_used_bytes", sa.BigInteger, nullable=False),
        sa.Column("avg_temperature", sa.Float, nullable=False),
    )

    # ── item_playback_stats materialized view ─────────────────────────────────
    # Must come AFTER playback_events is created.
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
    op.drop_table("score_history")
    op.drop_table("transfers")
    op.drop_table("playback_events")
    op.drop_table("media_items")
