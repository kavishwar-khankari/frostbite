import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import DBSession
from core.transfer_manager import queue_transfer
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
    return transfer


@router.post("/sync/library")
async def trigger_library_sync() -> dict:
    """Trigger a full library sync in the background. Returns immediately."""
    from core.library_sync import run_library_sync
    asyncio.get_event_loop().create_task(run_library_sync())
    return {"status": "started"}


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
