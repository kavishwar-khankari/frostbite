import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from api.deps import DBSession
from core.transfer_manager import stop_rclone_job
from models.schemas import TransferResponse
from models.tables import MediaItem, Transfer

router = APIRouter()

_WITH_ITEM = joinedload(Transfer.media_item)


def _resp(transfer: Transfer) -> TransferResponse:
    item = transfer.media_item if transfer.media_item else None
    return TransferResponse.from_orm_with_item(transfer, item)


@router.get("/transfers", response_model=list[TransferResponse])
async def list_transfers(
    db: DBSession,
    status: str | None = Query(None),
    direction: str | None = Query(None, description="freeze or reheat"),
    trigger: str | None = Query(None, description="auto_score, manual, space_pressure"),
    sort: str = Query("queued_at", description="queued_at, priority"),
    order: str = Query("desc", description="asc or desc"),
    limit: int = Query(200, le=500),
) -> list[TransferResponse]:
    q = select(Transfer).options(_WITH_ITEM)
    if status:
        q = q.where(Transfer.status == status)
    if direction:
        q = q.where(Transfer.direction == direction)
    if trigger:
        q = q.where(Transfer.trigger == trigger)

    sort_col = Transfer.priority if sort == "priority" else Transfer.queued_at
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc()).limit(limit)

    result = await db.execute(q)
    return [_resp(t) for t in result.scalars().unique().all()]


@router.get("/transfers/{transfer_id}", response_model=TransferResponse)
async def get_transfer(transfer_id: uuid.UUID, db: DBSession) -> TransferResponse:
    result = await db.execute(
        select(Transfer).options(_WITH_ITEM).where(Transfer.id == transfer_id)
    )
    transfer = result.scalar_one_or_none()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return _resp(transfer)


@router.post("/transfers/{transfer_id}/cancel", response_model=TransferResponse)
async def cancel_transfer(transfer_id: uuid.UUID, db: DBSession) -> TransferResponse:
    result = await db.execute(
        select(Transfer).options(_WITH_ITEM).where(Transfer.id == transfer_id)
    )
    transfer = result.scalar_one_or_none()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.status not in ("queued", "active"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel transfer in status '{transfer.status}'")

    await stop_rclone_job(transfer.rclone_job_id)
    transfer.status = "cancelled"
    if transfer.media_item and transfer.media_item.storage_tier == "transferring":
        transfer.media_item.storage_tier = "hot" if transfer.direction == "freeze" else "cold"
        transfer.media_item.transfer_direction = None

    await db.commit()
    await db.refresh(transfer)
    return _resp(transfer)


class BulkIdsRequest(BaseModel):
    ids: list[uuid.UUID]


class BulkActionResult(BaseModel):
    cancelled: int = 0
    bumped: int = 0
    skipped: int = 0


@router.post("/transfers/bulk-cancel", response_model=BulkActionResult)
async def bulk_cancel_transfers(body: BulkIdsRequest, db: DBSession) -> BulkActionResult:
    result = await db.execute(
        select(Transfer).options(_WITH_ITEM).where(Transfer.id.in_(body.ids))
    )
    transfers = list(result.scalars().unique())
    cancelled = skipped = 0
    for t in transfers:
        if t.status not in ("queued", "active"):
            skipped += 1
            continue
        await stop_rclone_job(t.rclone_job_id)
        t.status = "cancelled"
        if t.media_item and t.media_item.storage_tier == "transferring":
            t.media_item.storage_tier = "hot" if t.direction == "freeze" else "cold"
            t.media_item.transfer_direction = None
        cancelled += 1
    await db.commit()
    return BulkActionResult(cancelled=cancelled, skipped=skipped)


@router.post("/transfers/bulk-bump", response_model=BulkActionResult)
async def bulk_bump_transfers(body: BulkIdsRequest, db: DBSession) -> BulkActionResult:
    """Set priority=100 on queued transfers so they run next."""
    result = await db.execute(
        select(Transfer).where(Transfer.id.in_(body.ids), Transfer.status == "queued")
    )
    transfers = list(result.scalars())
    for t in transfers:
        t.priority = 100
    await db.commit()
    return BulkActionResult(bumped=len(transfers), skipped=len(body.ids) - len(transfers))


@router.post("/transfers/{transfer_id}/retry", response_model=TransferResponse)
async def retry_transfer(transfer_id: uuid.UUID, db: DBSession) -> TransferResponse:
    from core.transfer_manager import queue_transfer

    result = await db.execute(
        select(Transfer).options(_WITH_ITEM).where(Transfer.id == transfer_id)
    )
    transfer = result.scalar_one_or_none()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot retry transfer in status '{transfer.status}'")

    new_transfer = await queue_transfer(
        db=db,
        media_item_id=transfer.media_item_id,
        direction=transfer.direction,
        trigger="manual",
        priority=100,
    )
    reload = await db.execute(
        select(Transfer).options(_WITH_ITEM).where(Transfer.id == new_transfer.id)
    )
    return _resp(reload.scalar_one())
