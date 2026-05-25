import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from api.deps import DBSession
from core.deletion_manager import (
    approve_deletion,
    protect_item,
    protect_item_from_candidate,
    protect_items,
    protect_series,
    protect_series_from_candidate,
    remove_exception,
    scan_deletion_candidates,
)
from models.schemas import (
    BulkItemExceptionRequest,
    DeletionActionResult,
    DeletionCandidatePage,
    DeletionCandidateResponse,
    DeletionExceptionPage,
    DeletionExceptionResponse,
    DeletionScanResult,
    DeletionStatsResponse,
    ItemExceptionRequest,
    SeriesExceptionRequest,
)
from models.tables import DeletionCandidate, DeletionException

router = APIRouter()


@router.get("/deletion/candidates", response_model=DeletionCandidatePage)
async def list_candidates(
    db: DBSession,
    status: str | None = Query(None, description="pending, failed, deleted, protected, superseded"),
    search: str | None = Query(None),
    limit: int = Query(100, le=2000),
    offset: int = Query(0, ge=0),
) -> DeletionCandidatePage:
    base = select(DeletionCandidate)
    if status:
        base = base.where(DeletionCandidate.status == status)
    else:
        base = base.where(DeletionCandidate.status == "pending")
    if search:
        pattern = f"%{search}%"
        base = base.where(
            DeletionCandidate.title.ilike(pattern)
            | DeletionCandidate.series_name.ilike(pattern)
        )

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    q = base.order_by(DeletionCandidate.temperature.asc(), DeletionCandidate.created_at.desc())
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    items = [DeletionCandidateResponse.model_validate(c) for c in result.scalars().all()]
    return DeletionCandidatePage(items=items, total=total, limit=limit, offset=offset)


@router.post("/deletion/scan", response_model=DeletionScanResult)
async def manual_scan(db: DBSession) -> DeletionScanResult:
    result = await scan_deletion_candidates(db=db)
    return DeletionScanResult(**result)


@router.post("/deletion/candidates/{candidate_id}/approve", response_model=DeletionActionResult)
async def approve_candidate(candidate_id: uuid.UUID, db: DBSession) -> DeletionActionResult:
    try:
        candidate = await approve_deletion(candidate_id, db)
        return DeletionActionResult(
            status="deleted",
            candidate_id=candidate.id,
            deleted=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/deletion/candidates/{candidate_id}/protect-item", response_model=DeletionActionResult)
async def protect_candidate_item(candidate_id: uuid.UUID, db: DBSession) -> DeletionActionResult:
    try:
        exc = await protect_item_from_candidate(candidate_id, db)
        return DeletionActionResult(
            status="protected",
            candidate_id=candidate_id,
            protected=True,
            message=f"Item protected (exception {exc.id})",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/deletion/candidates/{candidate_id}/protect-series", response_model=DeletionActionResult)
async def protect_candidate_series(candidate_id: uuid.UUID, db: DBSession) -> DeletionActionResult:
    try:
        exc = await protect_series_from_candidate(candidate_id, db)
        return DeletionActionResult(
            status="protected",
            candidate_id=candidate_id,
            protected=True,
            message=f"Series protected (exception {exc.id})",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/deletion/exceptions", response_model=DeletionExceptionPage)
async def list_exceptions(
    db: DBSession,
    scope: str | None = Query(None, description="item, series"),
    search: str | None = Query(None),
    limit: int = Query(100, le=2000),
    offset: int = Query(0, ge=0),
) -> DeletionExceptionPage:
    base = select(DeletionException)
    if scope:
        base = base.where(DeletionException.scope == scope)
    if search:
        pattern = f"%{search}%"
        base = base.where(
            DeletionException.title.ilike(pattern)
            | DeletionException.jellyfin_id.ilike(pattern)
            | DeletionException.series_id.ilike(pattern)
        )

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    q = base.order_by(DeletionException.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    items = [DeletionExceptionResponse.model_validate(e) for e in result.scalars().all()]
    return DeletionExceptionPage(items=items, total=total, limit=limit, offset=offset)


@router.post("/deletion/exceptions/item", response_model=DeletionExceptionResponse)
async def add_item_exception(body: ItemExceptionRequest, db: DBSession) -> DeletionExceptionResponse:
    from models.tables import MediaItem

    item_result = await db.execute(
        select(MediaItem).where(MediaItem.jellyfin_id == body.jellyfin_id)
    )
    item = item_result.scalar_one_or_none()
    title = item.title if item else None

    exc = await protect_item(jellyfin_id=body.jellyfin_id, db=db, title=title, reason=body.reason)
    await db.commit()
    await db.refresh(exc)

    pending_result = await db.execute(
        select(DeletionCandidate).where(
            DeletionCandidate.jellyfin_id == body.jellyfin_id,
            DeletionCandidate.status == "pending",
        )
    )
    from datetime import datetime
    for c in pending_result.scalars():
        c.status = "protected"
        c.updated_at = datetime.utcnow()
    await db.commit()

    return DeletionExceptionResponse.model_validate(exc)


@router.post("/deletion/exceptions/bulk-items", response_model=DeletionActionResult)
async def add_bulk_item_exceptions(body: BulkItemExceptionRequest, db: DBSession) -> DeletionActionResult:
    result = await protect_items(body.jellyfin_ids, db=db, reason=body.reason)
    await db.commit()
    return DeletionActionResult(
        status="ok",
        protected=True,
        message=f"{result['created']} created, {result['skipped']} skipped",
    )


@router.post("/deletion/exceptions/series", response_model=DeletionExceptionResponse)
async def add_series_exception(body: SeriesExceptionRequest, db: DBSession) -> DeletionExceptionResponse:
    exc = await protect_series(series_id=body.series_id, db=db, title=body.series_id, reason=body.reason)
    await db.commit()
    await db.refresh(exc)

    from datetime import datetime
    pending_result = await db.execute(
        select(DeletionCandidate).where(
            DeletionCandidate.series_id == body.series_id,
            DeletionCandidate.status == "pending",
        )
    )
    for c in pending_result.scalars():
        c.status = "protected"
        c.updated_at = datetime.utcnow()
    await db.commit()

    return DeletionExceptionResponse.model_validate(exc)


@router.delete("/deletion/exceptions/{exception_id}")
async def delete_exception(exception_id: uuid.UUID, db: DBSession) -> dict:
    try:
        await remove_exception(exception_id, db)
        return {"status": "removed"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/deletion/stats", response_model=DeletionStatsResponse)
async def deletion_stats(db: DBSession) -> DeletionStatsResponse:
    pending_result = await db.execute(
        select(func.count()).select_from(DeletionCandidate)
        .where(DeletionCandidate.status == "pending")
    )
    failed_result = await db.execute(
        select(func.count()).select_from(DeletionCandidate)
        .where(DeletionCandidate.status == "failed")
    )
    deleted_result = await db.execute(
        select(func.count()).select_from(DeletionCandidate)
        .where(DeletionCandidate.status == "deleted")
    )
    item_exc_result = await db.execute(
        select(func.count()).select_from(DeletionException)
        .where(DeletionException.scope == "item")
    )
    series_exc_result = await db.execute(
        select(func.count()).select_from(DeletionException)
        .where(DeletionException.scope == "series")
    )

    return DeletionStatsResponse(
        pending_candidates=pending_result.scalar_one() or 0,
        failed_candidates=failed_result.scalar_one() or 0,
        deleted_candidates=deleted_result.scalar_one() or 0,
        item_exceptions=item_exc_result.scalar_one() or 0,
        series_exceptions=series_exc_result.scalar_one() or 0,
    )
