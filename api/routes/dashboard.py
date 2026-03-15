import os

from fastapi import APIRouter
from sqlalchemy import case, func, select

from api.deps import DBSession
from models.schemas import DashboardStats, TransferResponse
from models.tables import MediaItem, Transfer

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
        .where(Transfer.status == "active")
        .order_by(Transfer.started_at.desc())
    )
    active_transfers = list(active_result.scalars().all())

    # Queued count
    queued_result = await db.execute(
        select(func.count()).where(Transfer.status == "queued")
    )
    queued_count = queued_result.scalar_one()

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
        active_transfers=[TransferResponse.model_validate(t) for t in active_transfers],
        queued_transfers=queued_count,
    )
