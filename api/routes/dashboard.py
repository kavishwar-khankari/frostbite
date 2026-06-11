from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from api.deps import DBSession
from config import settings
from core.filesystem import bytes_to_gib, stat_storage
from core.prefetch_state import prefetch_protection_map
from models.schemas import DashboardStats, TransferResponse
from models.tables import MediaItem, Transfer

_WITH_ITEM = joinedload(Transfer.media_item)

router = APIRouter()

_CLOUD_CACHE_BYTES: int | None = None
_CLOUD_CACHE_AT: datetime | None = None
_CLOUD_CACHE_TTL = timedelta(seconds=60)


async def _cloud_used_bytes() -> tuple[int | None, str]:
    """Return cloud usage with a short TTL so dashboard polling does not spam rclone."""
    global _CLOUD_CACHE_BYTES, _CLOUD_CACHE_AT
    now = datetime.utcnow()
    if _CLOUD_CACHE_BYTES is not None and _CLOUD_CACHE_AT and now - _CLOUD_CACHE_AT < _CLOUD_CACHE_TTL:
        return _CLOUD_CACHE_BYTES, "cached"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.rclone_rc_url}/operations/about",
                json={"fs": f"{settings.rclone_remote}:"},
            )
            if resp.status_code == 200:
                data = resp.json()
                _CLOUD_CACHE_BYTES = data.get("used", 0) or 0
                _CLOUD_CACHE_AT = now
                return _CLOUD_CACHE_BYTES, "live"
    except Exception:
        pass

    if _CLOUD_CACHE_BYTES is not None:
        return _CLOUD_CACHE_BYTES, "cached"
    return None, "unavailable"


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(db: DBSession) -> DashboardStats:
    # Aggregate item counts + avg temperature
    counts = await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((MediaItem.storage_tier == "hot", 1), else_=0)).label("hot"),
            func.sum(case((MediaItem.storage_tier == "cold", 1), else_=0)).label("cold"),
            func.sum(case((MediaItem.storage_tier == "transferring", 1), else_=0)).label("transferring"),
            func.avg(MediaItem.temperature).label("avg_temp"),
        ).where(MediaItem.storage_tier != "deleted")
    )
    row = counts.one()

    # Active transfers
    active_result = await db.execute(
        select(Transfer)
        .options(_WITH_ITEM)
        .where(Transfer.status == "active")
        .order_by(Transfer.started_at.desc())
    )
    active_transfers = list(active_result.scalars().unique().all())

    # Queued count + first upcoming transfers per direction
    queued_result = await db.execute(
        select(func.count()).where(Transfer.status == "queued")
    )
    queued_count = queued_result.scalar_one()

    _ORDER = [Transfer.priority.desc(), Transfer.queued_at.asc(), Transfer.id.asc()]

    freeze_list_result = await db.execute(
        select(Transfer)
        .options(_WITH_ITEM)
        .where(Transfer.status == "queued", Transfer.direction == "freeze")
        .order_by(*_ORDER)
        .limit(10)
    )
    reheat_list_result = await db.execute(
        select(Transfer)
        .options(_WITH_ITEM)
        .where(Transfer.status == "queued", Transfer.direction == "reheat")
        .order_by(*_ORDER)
        .limit(10)
    )
    # Interleave: freeze[0], reheat[0], freeze[1], reheat[1], ... up to 10 total
    freezes = list(freeze_list_result.scalars().unique().all())
    reheats = list(reheat_list_result.scalars().unique().all())
    queued_transfers_list = [
        t for pair in zip(freezes, reheats) for t in pair
    ] + freezes[len(reheats):] + reheats[len(freezes):]
    queued_transfers_list = queued_transfers_list[:10]
    transfer_items = list({
        t.media_item.id: t.media_item
        for t in [*active_transfers, *queued_transfers_list, *freezes]
        if t.media_item
    }.values())
    prefetch_map = await prefetch_protection_map(db, transfer_items)

    # Tdarr-eligible count
    tdarr_result = await db.execute(
        select(func.count()).where(MediaItem.tdarr_eligible == True)  # noqa: E712
    )
    tdarr_eligible_count = tdarr_result.scalar_one()

    nas_usage = stat_storage(settings.nas_root)
    cloud_used_bytes, cloud_usage_source = await _cloud_used_bytes()
    storage_checked_at = datetime.utcnow()
    nas_free_gib = bytes_to_gib(nas_usage.available_bytes) if nas_usage else 0.0

    return DashboardStats(
        total_items=row.total or 0,
        hot_items=row.hot or 0,
        cold_items=row.cold or 0,
        transferring_items=row.transferring or 0,
        avg_temperature=float(row.avg_temp or 0.0),
        nas_used_bytes=nas_usage.used_bytes if nas_usage else None,
        nas_total_bytes=nas_usage.total_bytes if nas_usage else None,
        nas_available_bytes=nas_usage.available_bytes if nas_usage else None,
        cloud_used_bytes=cloud_used_bytes,
        storage_checked_at=storage_checked_at,
        cloud_usage_source=cloud_usage_source,
        nas_free_gb=nas_free_gib or 0.0,
        active_transfers=[
            TransferResponse.from_orm_with_item(t, t.media_item, prefetch_map.get(t.media_item_id))
            for t in active_transfers
        ],
        queued_transfers=queued_count,
        queued_transfer_list=[
            TransferResponse.from_orm_with_item(t, t.media_item, prefetch_map.get(t.media_item_id))
            for t in queued_transfers_list
        ],
        queued_freeze_list=[
            TransferResponse.from_orm_with_item(t, t.media_item, prefetch_map.get(t.media_item_id))
            for t in freezes
        ],
        tdarr_eligible_count=tdarr_eligible_count,
    )
