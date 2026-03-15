import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text

from api.deps import DBSession
from models.schemas import MediaItemResponse
from models.tables import MediaItem

router = APIRouter()

_SORT_COLUMNS = {
    "temperature": MediaItem.temperature,
    "title": MediaItem.title,
    "file_size_bytes": MediaItem.file_size_bytes,
    "date_added": MediaItem.date_added,
    "last_scored_at": MediaItem.last_scored_at,
    "episode_number": MediaItem.episode_number,
    "season_number": MediaItem.season_number,
}


class ItemsPage(BaseModel):
    total: int
    items: list[MediaItemResponse]


class TemperatureOverride(BaseModel):
    temperature: float


@router.get("/items", response_model=ItemsPage)
async def list_items(
    db: DBSession,
    tier: str | None = Query(None),
    item_type: str | None = Query(None, description="movie, episode"),
    series_id: str | None = Query(None),
    search: str | None = Query(None),
    sort: str = Query("temperature", description="temperature, title, file_size_bytes, date_added"),
    order: str = Query("desc", description="asc or desc"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
) -> ItemsPage:
    col = _SORT_COLUMNS.get(sort, MediaItem.temperature)
    direction = col.desc() if order == "desc" else col.asc()

    base = select(MediaItem)
    if tier:
        base = base.where(MediaItem.storage_tier == tier)
    if item_type:
        base = base.where(MediaItem.item_type == item_type)
    if series_id:
        base = base.where(MediaItem.series_id == series_id)
    if search:
        base = base.where(MediaItem.title.ilike(f"%{search}%"))

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    q = base.order_by(direction).limit(limit).offset(offset)
    result = await db.execute(q)
    return ItemsPage(total=total, items=list(result.scalars().all()))


@router.get("/items/{jellyfin_id}/score-breakdown")
async def get_score_breakdown(jellyfin_id: str, db: DBSession) -> dict:
    """Return the per-factor temperature breakdown for a single item."""
    from core.scorer import ItemMeta, PlaybackStats, calculate_temperature_with_breakdown

    result = await db.execute(select(MediaItem).where(MediaItem.jellyfin_id == jellyfin_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    stats_row = None
    try:
        sr = await db.execute(
            text("SELECT * FROM item_playback_stats WHERE media_item_id = :id"),
            {"id": item.id},
        )
        stats_row = sr.mappings().one_or_none()
    except Exception:
        pass

    stats = PlaybackStats(
        last_played_at=stats_row["last_played_at"] if stats_row else None,
        total_plays=stats_row["total_plays"] if stats_row else 0,
        unique_viewers=stats_row["unique_viewers"] if stats_row else 0,
        plays_last_7d=stats_row["plays_last_7d"] if stats_row else 0,
        plays_last_30d=stats_row["plays_last_30d"] if stats_row else 0,
    )
    meta = ItemMeta(
        file_size_bytes=item.file_size_bytes,
        date_added=item.date_added,
        series_status=item.series_status,
        community_rating=item.community_rating,
    )
    score, breakdown = calculate_temperature_with_breakdown(meta, stats)
    return {
        "jellyfin_id": jellyfin_id,
        "temperature": round(score, 1),
        "breakdown": breakdown,
        "factors": {
            "recency":          {"label": "Recency (last played)",  "max": 30, "value": breakdown["recency"]},
            "play_count":       {"label": "Play count",             "max": 20, "value": breakdown["play_count"]},
            "unique_viewers":   {"label": "Unique viewers",         "max": 15, "value": breakdown["unique_viewers"]},
            "trending":         {"label": "Trending (7d velocity)", "max": 15, "value": breakdown["trending"]},
            "newness":          {"label": "Newness boost",          "max": 30, "value": breakdown["newness"]},
            "series_status":    {"label": "Series continuing",      "max":  5, "value": breakdown["series_status"]},
            "community_rating": {"label": "Community rating",       "max":  5, "value": breakdown["community_rating"]},
            "size_penalty":     {"label": "Size penalty",           "max":  0, "value": breakdown["size_penalty"]},
        },
    }


@router.patch("/items/{jellyfin_id}/temperature", response_model=MediaItemResponse)
async def override_temperature(
    jellyfin_id: str,
    body: TemperatureOverride,
    db: DBSession,
) -> MediaItem:
    if not (0.0 <= body.temperature <= 100.0):
        raise HTTPException(status_code=400, detail="temperature must be between 0 and 100")
    result = await db.execute(select(MediaItem).where(MediaItem.jellyfin_id == jellyfin_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.temperature = body.temperature
    await db.commit()
    await db.refresh(item)
    return item
