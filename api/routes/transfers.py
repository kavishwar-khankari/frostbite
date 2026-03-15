import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import DBSession
from models.schemas import TransferResponse
from models.tables import Transfer

router = APIRouter()


@router.get("/transfers", response_model=list[TransferResponse])
async def list_transfers(
    db: DBSession,
    status: str | None = None,
) -> list[Transfer]:
    q = select(Transfer).order_by(Transfer.queued_at.desc()).limit(200)
    if status:
        q = q.where(Transfer.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/transfers/{transfer_id}", response_model=TransferResponse)
async def get_transfer(transfer_id: uuid.UUID, db: DBSession) -> Transfer:
    result = await db.execute(select(Transfer).where(Transfer.id == transfer_id))
    transfer = result.scalar_one_or_none()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer


@router.post("/transfers/{transfer_id}/cancel", response_model=TransferResponse)
async def cancel_transfer(transfer_id: uuid.UUID, db: DBSession) -> Transfer:
    result = await db.execute(select(Transfer).where(Transfer.id == transfer_id))
    transfer = result.scalar_one_or_none()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.status not in ("queued", "active"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel transfer in status '{transfer.status}'")

    transfer.status = "cancelled"
    await db.commit()
    await db.refresh(transfer)
    return transfer


@router.post("/transfers/{transfer_id}/retry", response_model=TransferResponse)
async def retry_transfer(transfer_id: uuid.UUID, db: DBSession) -> Transfer:
    from core.transfer_manager import queue_transfer

    result = await db.execute(select(Transfer).where(Transfer.id == transfer_id))
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
    return new_transfer
