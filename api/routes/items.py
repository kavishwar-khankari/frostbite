import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

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
