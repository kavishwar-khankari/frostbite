import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from api.deps import DBSession
from core.transfer_manager import stop_rclone_job
from models.schemas import TransferPage, TransferResponse
from models.tables import MediaItem, Transfer

router = APIRouter()

_WITH_ITEM = joinedload(Transfer.media_item)


def _resp(transfer: Transfer) -> TransferResponse:
    item = transfer.media_item if transfer.media_item else None
    return TransferResponse.from_orm_with_item(transfer, item)


@router.get("/transfers", response_model=TransferPage)
async def list_transfers(
    db: DBSession,
    status: str | None = Query(None),
    direction: str | None = Query(None, description="freeze or reheat"),
    trigger: str | None = Query(None, description="auto_score, manual, space_pressure"),
    search: str | None = Query(None, description="Search by item title or series name"),
    sort: str = Query("queued_at", description="queued_at, priority"),
    order: str = Query("desc", description="asc or desc"),
    limit: int = Query(200, le=2000),
    offset: int = Query(0, ge=0),
) -> TransferPage:
    # Base filter (reused for both count and items query)
    def _apply_filters(q):
        if status:
            q = q.where(Transfer.status == status)
        if direction:
            q = q.where(Transfer.direction == direction)
        if trigger:
            q = q.where(Transfer.trigger == trigger)
        if search:
            pattern = f"%{search}%"
            q = q.where(Transfer.media_item.has(
                MediaItem.title.ilike(pattern) | MediaItem.series_name.ilike(pattern)
            ))
        return q

    # Total count
    count_q = _apply_filters(select(func.count()).select_from(Transfer))
    total = (await db.execute(count_q)).scalar_one()

    # Items
    if sort == "priority":
        sort_col = Transfer.priority
    elif sort == "completed_at":
        sort_col = Transfer.completed_at
    else:
        sort_col = Transfer.queued_at
    order_clause = sort_col.desc() if order == "desc" else sort_col.asc()
    items_q = _apply_filters(select(Transfer).options(_WITH_ITEM))
    items_q = items_q.order_by(order_clause, Transfer.queued_at.asc(), Transfer.id.asc())
    items_q = items_q.limit(limit).offset(offset)

    result = await db.execute(items_q)
    items = [_resp(t) for t in result.scalars().unique().all()]

    return TransferPage(items=items, total=total, limit=limit, offset=offset)


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
    retried: int = 0
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


@router.post("/transfers/bulk-retry", response_model=BulkActionResult)
async def bulk_retry_transfers(body: BulkIdsRequest, db: DBSession) -> BulkActionResult:
    """Re-queue failed/cancelled transfers."""
    from core.transfer_manager import queue_transfer
    import logging
    logger = logging.getLogger(__name__)

    result = await db.execute(
        select(Transfer).where(Transfer.id.in_(body.ids))
    )
    transfers = list(result.scalars())
    retried = skipped = 0
    for t in transfers:
        if t.status not in ("failed", "cancelled"):
            skipped += 1
            continue
        try:
            new = await queue_transfer(
                db=db,
                media_item_id=t.media_item_id,
                direction=t.direction,
                trigger="manual",
                priority=t.priority,
            )
            if new:
                t.status = "retried"
                retried += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.warning("Bulk retry: failed to re-queue transfer %s: %s", t.id, exc)
            skipped += 1
    await db.commit()
    logger.info("Bulk retry: %d retried, %d skipped out of %d", retried, skipped, len(transfers))
    return BulkActionResult(retried=retried, skipped=skipped)


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
    if not new_transfer:
        raise HTTPException(status_code=409, detail="A transfer is already queued or active for this item")
    transfer.status = "retried"
    await db.commit()
    reload = await db.execute(
        select(Transfer).options(_WITH_ITEM).where(Transfer.id == new_transfer.id)
    )
    return _resp(reload.scalar_one())
