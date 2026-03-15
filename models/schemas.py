import uuid
from datetime import datetime

from pydantic import BaseModel


# ── Media Items ──────────────────────────────────────────────────────────────

class MediaItemResponse(BaseModel):
    id: uuid.UUID
    jellyfin_id: str
    title: str
    item_type: str
    series_name: str | None
    season_number: int | None
    episode_number: int | None
    file_path: str
    file_size_bytes: int
    storage_tier: str
    transfer_direction: str | None
    temperature: float
    last_scored_at: datetime | None

    model_config = {"from_attributes": True}


class ItemStatusResponse(BaseModel):
    id: uuid.UUID
    jellyfin_id: str
    storage_tier: str
    transfer_direction: str | None
    temperature: float
    active_transfer_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


# ── Transfers ────────────────────────────────────────────────────────────────

class TransferResponse(BaseModel):
    id: uuid.UUID
    media_item_id: uuid.UUID
    direction: str
    trigger: str
    priority: int
    status: str
    bytes_transferred: int
    bytes_total: int
    speed_bps: int
    eta_seconds: int | None
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ManualTransferRequest(BaseModel):
    jellyfin_id: str
    direction: str  # 'freeze' or 'reheat'


# ── Dashboard ────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_items: int
    hot_items: int
    cold_items: int
    transferring_items: int
    avg_temperature: float
    nas_free_gb: float
    active_transfers: list[TransferResponse]
    queued_transfers: int


# ── Webhook (Jellyfin) ───────────────────────────────────────────────────────

class PlaybackEventIn(BaseModel):
    """Normalised playback event parsed from a Jellyfin webhook payload."""
    jellyfin_id: str
    user_id: str
    username: str | None
    event_type: str          # start, stop, progress
    play_method: str | None
    position_ticks: int | None
    duration_ticks: int | None
    client_name: str | None
    device_name: str | None
    item_type: str | None
    title: str | None
    series_id: str | None
    series_name: str | None
    season_number: int | None
    episode_number: int | None
    file_path: str | None

    @classmethod
    def from_webhook(cls, payload: dict) -> "PlaybackEventIn":
        item = payload.get("Item") or {}
        session = payload.get("Session") or {}
        media_streams = item.get("MediaStreams") or []

        # Resolve file path from MediaSources if available
        sources = item.get("MediaSources") or []
        file_path = sources[0].get("Path") if sources else item.get("Path")

        return cls(
            jellyfin_id=item.get("Id") or payload.get("ItemId", ""),
            user_id=session.get("UserId") or payload.get("UserId", ""),
            username=session.get("UserName") or payload.get("NotificationUsername"),
            event_type={
                "PlaybackStart": "start",
                "PlaybackStop": "stop",
                "PlaybackProgress": "progress",
            }.get(payload.get("NotificationType", ""), "unknown"),
            play_method=session.get("PlayState", {}).get("PlayMethod"),
            position_ticks=session.get("PlayState", {}).get("PositionTicks"),
            duration_ticks=item.get("RunTimeTicks"),
            client_name=session.get("Client"),
            device_name=session.get("DeviceName"),
            item_type=item.get("Type", "").lower() or None,
            title=item.get("Name"),
            series_id=item.get("SeriesId"),
            series_name=item.get("SeriesName"),
            season_number=item.get("ParentIndexNumber"),
            episode_number=item.get("IndexNumber"),
            file_path=file_path,
        )
