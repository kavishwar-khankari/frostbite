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
        # Jellyfin sends a flat JSON via the manual Handlebars template.
        # All values arrive as top-level keys.  Nested Item/Session dicts
        # are kept as fallbacks in case someone points a stock webhook at us.
        item = payload.get("Item") or {}
        session = payload.get("Session") or {}

        def _int(val: object) -> int | None:
            """Safely coerce string/float/None → int."""
            try:
                return int(val) if val not in (None, "", "0") else None
            except (TypeError, ValueError):
                return None

        # Nested MediaSources path (stock webhook) → not available in flat mode.
        # Flat template: Jellyfin exposes {{ItemPath}} or {{Path}}.
        sources = item.get("MediaSources") or []
        file_path = (
            sources[0].get("Path") if sources
            else item.get("Path")
            or payload.get("ItemPath")
            or payload.get("Path")
        )

        return cls(
            jellyfin_id=(
                payload.get("ItemId")
                or item.get("Id")
                or ""
            ),
            user_id=(
                payload.get("UserId")
                or session.get("UserId")
                or ""
            ),
            username=(
                payload.get("NotificationUsername")
                or session.get("UserName")
            ),
            event_type={
                "PlaybackStart": "start",
                "PlaybackStop": "stop",
                "PlaybackProgress": "progress",
            }.get(payload.get("NotificationType", ""), "unknown"),
            play_method=(
                payload.get("PlayMethod")
                or session.get("PlayState", {}).get("PlayMethod")
            ),
            position_ticks=_int(
                payload.get("PositionTicks")
                or payload.get("PlaybackPositionTicks")
                or session.get("PlayState", {}).get("PositionTicks")
            ),
            duration_ticks=_int(
                payload.get("RunTimeTicks")
                or item.get("RunTimeTicks")
            ),
            client_name=(
                payload.get("ClientName")
                or session.get("Client")
            ),
            device_name=(
                payload.get("DeviceName")
                or session.get("DeviceName")
            ),
            item_type=(
                (payload.get("ItemType") or item.get("Type") or "").lower() or None
            ),
            title=(
                payload.get("Name")
                or payload.get("ItemName")
                or item.get("Name")
            ),
            series_id=(
                payload.get("SeriesId")
                or item.get("SeriesId")
            ),
            series_name=(
                payload.get("SeriesName")
                or item.get("SeriesName")
            ),
            season_number=_int(
                payload.get("SeasonNumber")
                or item.get("ParentIndexNumber")
            ),
            episode_number=_int(
                payload.get("EpisodeNumber")
                or item.get("IndexNumber")
            ),
            file_path=file_path,
        )
