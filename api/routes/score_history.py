from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import DBSession
from models.tables import ScoreHistory

router = APIRouter()


class ScoreHistoryPoint(BaseModel):
    recorded_at: datetime
    total_items: int
    hot_items: int
    cold_items: int
    nas_used_bytes: int
    cloud_used_bytes: int
    avg_temperature: float


@router.get("/score-history", response_model=list[ScoreHistoryPoint])
async def get_score_history(
    db: DBSession,
    days: int = Query(30, ge=1, le=90),
) -> list[ScoreHistoryPoint]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(ScoreHistory)
        .where(ScoreHistory.recorded_at >= cutoff)
        .order_by(ScoreHistory.recorded_at.asc())
    )
    return list(result.scalars().all())
