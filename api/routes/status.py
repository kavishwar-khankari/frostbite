from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import DBSession
from models.schemas import ItemStatusResponse
from models.tables import MediaItem, Transfer

router = APIRouter()


@router.get("/status/{jellyfin_id}", response_model=ItemStatusResponse)
async def get_item_status(jellyfin_id: str, db: DBSession) -> dict:
    result = await db.execute(
        select(MediaItem).where(MediaItem.jellyfin_id == jellyfin_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Find active transfer if any
    active_result = await db.execute(
        select(Transfer.id)
        .where(Transfer.media_item_id == item.id, Transfer.status == "active")
        .limit(1)
    )
    active_transfer_id = active_result.scalar_one_or_none()

    return {
        "id": item.id,
        "jellyfin_id": item.jellyfin_id,
        "storage_tier": item.storage_tier,
        "transfer_direction": item.transfer_direction,
        "temperature": item.temperature,
        "active_transfer_id": active_transfer_id,
    }
