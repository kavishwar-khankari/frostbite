import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import DBSession
from sqlalchemy import select

from core.transfer_manager import is_paused, pause_all_transfers, queue_transfer, resume_transfers
from models.tables import Transfer
from models.schemas import ManualTransferRequest, TransferResponse
from models.tables import MediaItem

router = APIRouter()


class BulkActionRequest(BaseModel):
    jellyfin_ids: list[str]


class BulkActionResponse(BaseModel):
    queued: int
    skipped: int
    errors: list[str]


async def _queue_manual(jellyfin_id: str, direction: str, db: DBSession) -> TransferResponse:
    result = await db.execute(select(MediaItem).where(MediaItem.jellyfin_id == jellyfin_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.storage_tier == ("hot" if direction == "reheat" else "cold"):
        raise HTTPException(status_code=400, detail=f"Item is already {item.storage_tier}")

    transfer = await queue_transfer(
        db=db,
        media_item_id=item.id,
        direction=direction,
        trigger="manual",
        priority=100,
    )
    if not transfer:
        raise HTTPException(status_code=409, detail="A transfer is already queued or active for this item")
    return transfer


@router.post("/transfers/pause-all")
async def pause_all(db: DBSession) -> dict:
    """Stop all active rclone jobs and pause the transfer worker."""
    stopped = await pause_all_transfers(db)
    return {"status": "paused", "stopped": stopped}


@router.post("/transfers/resume")
async def resume() -> dict:
    """Resume the transfer worker."""
    resume_transfers()
    return {"status": "running"}


@router.get("/transfers/worker-status")
async def worker_status() -> dict:
    return {"paused": is_paused()}


class SeriesActionRequest(BaseModel):
    series_id: str
    season_number: int | None = None


async def _series_action(body: SeriesActionRequest, direction: str, db: DBSession) -> dict:
    from models.tables import MediaItem
    tier = "hot" if direction == "freeze" else "cold"
    q = select(MediaItem).where(
        MediaItem.series_id == body.series_id,
        MediaItem.storage_tier == tier,
    )
    if body.season_number is not None:
        q = q.where(MediaItem.season_number == body.season_number)
    result = await db.execute(q)
    items = list(result.scalars())

    # Get IDs with pending transfers to avoid duplicates
    pending_result = await db.execute(
        select(Transfer.media_item_id).where(Transfer.status.in_(["queued", "active"]))
    )
    pending_ids = set(pending_result.scalars())

    queued = skipped = 0
    for item in items:
        if item.id in pending_ids:
            skipped += 1
            continue
        await queue_transfer(db, item.id, direction, "manual", priority=90)
        queued += 1
    await db.commit()
    return {"queued": queued, "skipped": skipped}


@router.post("/freeze-series")
async def freeze_series(body: SeriesActionRequest, db: DBSession) -> dict:
    return await _series_action(body, "freeze", db)


@router.post("/reheat-series")
async def reheat_series(body: SeriesActionRequest, db: DBSession) -> dict:
    return await _series_action(body, "reheat", db)


@router.post("/tdarr/sync")
async def trigger_tdarr_sync() -> dict:
    """Trigger a Tdarr eligibility sync. Runs synchronously and returns result."""
    from core.scheduler import sync_tdarr_eligibility
    try:
        await sync_tdarr_eligibility()
        return {"status": "completed"}
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


@router.post("/playback/import-history")
async def import_playback_history() -> dict:
    """
    Trigger a full reimport of all historical play sessions from the Jellyfin
    Playback Reporting plugin.  Resets the sync cursor so everything is
    re-fetched from the beginning of time.
    """
    from core.playback_import import sync_playback_from_reporting
    try:
        result = await sync_playback_from_reporting(full_reimport=True)
        return {"status": "completed", **(result if isinstance(result, dict) else {})}
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


@router.post("/scoring/run")
async def trigger_scoring_sweep() -> dict:
    """Trigger a scoring sweep immediately."""
    from core.scheduler import scoring_sweep
    try:
        await scoring_sweep()
        return {"status": "completed"}
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


@router.post("/sync/library")
async def trigger_library_sync() -> dict:
    """Trigger a full library sync. Returns result when complete."""
    from core.library_sync import run_library_sync
    try:
        result = await run_library_sync()
        return {"status": "completed", **(result if isinstance(result, dict) else {})}
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


@router.post("/reheat", response_model=TransferResponse)
async def manual_reheat(body: ManualTransferRequest, db: DBSession) -> TransferResponse:
    return await _queue_manual(body.jellyfin_id, "reheat", db)


@router.post("/freeze", response_model=TransferResponse)
async def manual_freeze(body: ManualTransferRequest, db: DBSession) -> TransferResponse:
    return await _queue_manual(body.jellyfin_id, "freeze", db)


@router.post("/bulk-reheat", response_model=BulkActionResponse)
async def bulk_reheat(body: BulkActionRequest, db: DBSession) -> BulkActionResponse:
    return await _bulk_action(body.jellyfin_ids, "reheat", db)


@router.post("/bulk-freeze", response_model=BulkActionResponse)
async def bulk_freeze(body: BulkActionRequest, db: DBSession) -> BulkActionResponse:
    return await _bulk_action(body.jellyfin_ids, "freeze", db)


async def _bulk_action(ids: list[str], direction: str, db: DBSession) -> BulkActionResponse:
    queued, skipped, errors = 0, 0, []
    already_tier = "hot" if direction == "reheat" else "cold"
    for jid in ids:
        try:
            result = await db.execute(select(MediaItem).where(MediaItem.jellyfin_id == jid))
            item = result.scalar_one_or_none()
            if not item:
                errors.append(f"{jid}: not found")
                continue
            if item.storage_tier == already_tier:
                skipped += 1
                continue
            await queue_transfer(db=db, media_item_id=item.id, direction=direction, trigger="manual", priority=90)
            queued += 1
        except Exception as exc:
            errors.append(f"{jid}: {exc}")
    return BulkActionResponse(queued=queued, skipped=skipped, errors=errors)
