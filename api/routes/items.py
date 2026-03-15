from fastapi import APIRouter, Query
from sqlalchemy import select

from api.deps import DBSession
from models.schemas import MediaItemResponse
from models.tables import MediaItem

router = APIRouter()


@router.get("/items", response_model=list[MediaItemResponse])
async def list_items(
    db: DBSession,
    tier: str | None = Query(None, description="Filter by storage_tier: hot, cold, transferring"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
) -> list[MediaItem]:
    q = select(MediaItem).order_by(MediaItem.temperature.desc()).limit(limit).offset(offset)
    if tier:
        q = q.where(MediaItem.storage_tier == tier)
    result = await db.execute(q)
    return list(result.scalars().all())
