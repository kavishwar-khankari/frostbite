import uuid

from fastapi import APIRouter, HTTPException
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
    status: str | None = None,
) -> list[TransferResponse]:
    q = (
        select(Transfer)
        .options(_WITH_ITEM)
        .order_by(Transfer.queued_at.desc())
        .limit(200)
    )
    if status:
        q = q.where(Transfer.status == status)
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

    # Stop the rclone job before marking cancelled (best-effort)
    await stop_rclone_job(transfer.rclone_job_id)

    transfer.status = "cancelled"
    # Roll back the media item tier if it was mid-transfer
    if transfer.media_item:
        item = transfer.media_item
        if item.storage_tier == "transferring":
            item.storage_tier = "hot" if transfer.direction == "freeze" else "cold"
            item.transfer_direction = None

    await db.commit()
    await db.refresh(transfer)
    return _resp(transfer)


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
    # Reload with item
    reload = await db.execute(
        select(Transfer).options(_WITH_ITEM).where(Transfer.id == new_transfer.id)
    )
    return _resp(reload.scalar_one())
