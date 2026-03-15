import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Float, ForeignKey, Index, Integer,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base


class MediaItem(Base):
    __tablename__ = "media_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jellyfin_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)  # movie, episode, season, series
    series_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    series_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    season_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # File info
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    codec: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Tdarr encoding gate — file is invisible to scoring/freezing until Tdarr marks it done
    tdarr_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tdarr_status: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 'pending', 'encoding', 'done', 'not_required'

    # Storage state
    storage_tier: Mapped[str] = mapped_column(String(10), nullable=False, default="hot")
    transfer_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Scoring
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    last_scored_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Jellyfin metadata
    date_added: Mapped[datetime | None] = mapped_column(nullable=True)
    premiere_date: Mapped[datetime | None] = mapped_column(nullable=True)
    community_rating: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sonarr/Radarr metadata
    series_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    playback_events: Mapped[list["PlaybackEvent"]] = relationship(
        back_populates="media_item", cascade="all, delete-orphan"
    )
    transfers: Mapped[list["Transfer"]] = relationship(
        back_populates="media_item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_media_items_jellyfin_id", "jellyfin_id"),
        Index("idx_media_items_series_id", "series_id"),
        Index("idx_media_items_temperature", "temperature"),
        Index("idx_media_items_storage_tier", "storage_tier"),
    )


class PlaybackEvent(Base):
    __tablename__ = "playback_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    media_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # start, stop, progress
    play_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    position_ticks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_ticks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    client_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    media_item: Mapped["MediaItem"] = relationship(back_populates="playback_events")

    __table_args__ = (
        Index("idx_playback_events_media_item", "media_item_id", "created_at"),
        Index("idx_playback_events_created", "created_at"),
    )


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    media_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)   # freeze, reheat
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)     # auto_score, prefetch, manual, space_pressure
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # rclone job tracking
    rclone_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rclone_group: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # State
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")

    # Progress
    bytes_transferred: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_total: Mapped[int] = mapped_column(BigInteger, default=0)
    speed_bps: Mapped[int] = mapped_column(BigInteger, default=0)
    eta_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    queued_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    dest_path: Mapped[str] = mapped_column(Text, nullable=False)

    media_item: Mapped["MediaItem"] = relationship(back_populates="transfers")

    __table_args__ = (
        Index("idx_transfers_status", "status"),
        Index("idx_transfers_media_item", "media_item_id"),
    )


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    total_items: Mapped[int] = mapped_column(Integer, nullable=False)
    hot_items: Mapped[int] = mapped_column(Integer, nullable=False)
    cold_items: Mapped[int] = mapped_column(Integer, nullable=False)
    nas_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cloud_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    avg_temperature: Mapped[float] = mapped_column(Float, nullable=False)
