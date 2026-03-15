"""Series aggregation endpoint — groups episodes by series and season."""

import asyncio
import os

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select

from api.deps import DBSession
from config import settings
from models.tables import MediaItem

router = APIRouter()


def _extract_library(file_path: str) -> str:
    """Return the top-level folder name under jellyfin_media_root.
    e.g. /media_2/ANIME/Show/... → 'ANIME'
    """
    try:
        rel = os.path.relpath(file_path, settings.jellyfin_media_root)
        top = rel.split(os.sep)[0]
        return top if top != "." else "Other"
    except Exception:
        return "Other"


class SeasonSummary(BaseModel):
    season_number: int | None
    episode_count: int
    hot_count: int
    cold_count: int
    avg_temperature: float
    total_size_bytes: int


class SeriesSummary(BaseModel):
    series_id: str
    series_name: str | None
    library: str
    total_episodes: int
    hot_episodes: int
    cold_episodes: int
    avg_temperature: float
    total_size_bytes: int
    last_added: str | None
    seasons: list[SeasonSummary] = []


_SORT_MAP = {
    "temperature": func.avg(MediaItem.temperature).desc(),
    "name":        MediaItem.series_name.asc(),
    "size":        func.sum(MediaItem.file_size_bytes).desc(),
    "date":        func.max(MediaItem.date_added).desc(),
}


@router.get("/series", response_model=list[SeriesSummary])
async def list_series(
    db: DBSession,
    search: str | None = Query(None),
    sort: str = Query("temperature", description="temperature, name, size, date"),
) -> list[SeriesSummary]:
    order_by = _SORT_MAP.get(sort, _SORT_MAP["temperature"])

    series_q = (
        select(
            MediaItem.series_id,
            MediaItem.series_name,
            func.count().label("total"),
            func.sum(case((MediaItem.storage_tier == "hot", 1), else_=0)).label("hot"),
            func.sum(case((MediaItem.storage_tier == "cold", 1), else_=0)).label("cold"),
            func.avg(MediaItem.temperature).label("avg_temp"),
            func.sum(MediaItem.file_size_bytes).label("total_size"),
            func.min(MediaItem.file_path).label("sample_path"),
            func.max(MediaItem.date_added).label("last_added"),
        )
        .where(MediaItem.series_id.isnot(None))
        .group_by(MediaItem.series_id, MediaItem.series_name)
        .order_by(order_by)
    )
    season_q = (
        select(
            MediaItem.series_id,
            MediaItem.season_number,
            func.count().label("episode_count"),
            func.sum(case((MediaItem.storage_tier == "hot", 1), else_=0)).label("hot"),
            func.sum(case((MediaItem.storage_tier == "cold", 1), else_=0)).label("cold"),
            func.avg(MediaItem.temperature).label("avg_temp"),
            func.sum(MediaItem.file_size_bytes).label("total_size"),
        )
        .where(MediaItem.series_id.isnot(None))
        .group_by(MediaItem.series_id, MediaItem.season_number)
        .order_by(MediaItem.series_id, MediaItem.season_number)
    )
    if search:
        series_q = series_q.where(MediaItem.series_name.ilike(f"%{search}%"))
        season_q = season_q.where(MediaItem.series_name.ilike(f"%{search}%"))

    series_result, season_result = await asyncio.gather(
        db.execute(series_q),
        db.execute(season_q),
    )

    seasons_by_series: dict[str, list[SeasonSummary]] = {}
    for s in season_result.all():
        seasons_by_series.setdefault(s.series_id, []).append(
            SeasonSummary(
                season_number=s.season_number,
                episode_count=s.episode_count,
                hot_count=s.hot or 0,
                cold_count=s.cold or 0,
                avg_temperature=round(float(s.avg_temp or 0), 1),
                total_size_bytes=s.total_size or 0,
            )
        )

    return [
        SeriesSummary(
            series_id=row.series_id,
            series_name=row.series_name,
            library=_extract_library(row.sample_path or ""),
            total_episodes=row.total,
            hot_episodes=row.hot or 0,
            cold_episodes=row.cold or 0,
            avg_temperature=round(float(row.avg_temp or 0), 1),
            total_size_bytes=row.total_size or 0,
            last_added=row.last_added.strftime("%Y-%m-%d") if row.last_added else None,
            seasons=seasons_by_series.get(row.series_id, []),
        )
        for row in series_result.all()
    ]
