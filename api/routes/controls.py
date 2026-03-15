from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import DBSession
from core.transfer_manager import queue_transfer
from models.schemas import ManualTransferRequest, TransferResponse
from models.tables import MediaItem

router = APIRouter()


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


@router.post("/reheat", response_model=TransferResponse)
async def manual_reheat(body: ManualTransferRequest, db: DBSession) -> TransferResponse:
    return await _queue_manual(body.jellyfin_id, "reheat", db)


@router.post("/freeze", response_model=TransferResponse)
async def manual_freeze(body: ManualTransferRequest, db: DBSession) -> TransferResponse:
    return await _queue_manual(body.jellyfin_id, "freeze", db)
