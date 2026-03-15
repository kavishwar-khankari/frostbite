import os

from fastapi import APIRouter
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from api.deps import DBSession
from models.schemas import DashboardStats, TransferResponse
from models.tables import MediaItem, Transfer

_WITH_ITEM = joinedload(Transfer.media_item)

router = APIRouter()


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
        )
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

    # Tdarr-eligible count
    tdarr_result = await db.execute(
        select(func.count()).where(MediaItem.tdarr_eligible == True)  # noqa: E712
    )
    tdarr_eligible_count = tdarr_result.scalar_one()

    # NAS free space
    nas_free_gb = 0.0
    try:
        sv = os.statvfs("/mnt/nas/media")
        nas_free_gb = (sv.f_bavail * sv.f_frsize) / (1024 ** 3)
    except OSError:
        pass

    return DashboardStats(
        total_items=row.total or 0,
        hot_items=row.hot or 0,
        cold_items=row.cold or 0,
        transferring_items=row.transferring or 0,
        avg_temperature=float(row.avg_temp or 0.0),
        nas_free_gb=nas_free_gb,
        active_transfers=[TransferResponse.from_orm_with_item(t, t.media_item) for t in active_transfers],
        queued_transfers=queued_count,
        queued_transfer_list=[TransferResponse.from_orm_with_item(t, t.media_item) for t in queued_transfers_list],
        tdarr_eligible_count=tdarr_eligible_count,
    )
