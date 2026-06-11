"""Helpers for deriving prefetch protection state from playback events."""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.freeze_policy import prefetch_protected_until
from models.tables import MediaItem, PlaybackEvent

logger = logging.getLogger(__name__)


async def prefetch_protection_map(
    db: AsyncSession,
    items: list[MediaItem],
    now: datetime | None = None,
) -> dict[uuid.UUID, datetime | None]:
    """Return protected-until timestamps keyed by media item id.

    If playback lookup fails, fall back to time-based grace. That is safer than
    incorrectly treating a recently prefetched item as unprotected.
    """
    now = now or datetime.utcnow()
    prefetch_cutoff = now - timedelta(hours=settings.prefetch_grace_hours)
    recent_prefetches = {
        item.id: item.last_prefetch_at
        for item in items
        if item and item.last_prefetch_at and item.last_prefetch_at > prefetch_cutoff
    }
    watched_after_prefetch_ids: set[uuid.UUID] = set()

    if recent_prefetches:
        try:
            watched_result = await db.execute(
                select(PlaybackEvent.media_item_id, PlaybackEvent.created_at).where(
                    PlaybackEvent.media_item_id.in_(list(recent_prefetches)),
                    PlaybackEvent.event_type == "start",
                    PlaybackEvent.created_at > prefetch_cutoff,
                )
            )
            for media_item_id, created_at in watched_result.all():
                last_prefetch_at = recent_prefetches.get(media_item_id)
                if last_prefetch_at and created_at > last_prefetch_at:
                    watched_after_prefetch_ids.add(media_item_id)
        except Exception as exc:
            logger.warning("Could not check watched-after-prefetch state; using time grace only: %s", exc)

    return {
        item.id: prefetch_protected_until(
            item.last_prefetch_at,
            item.id in watched_after_prefetch_ids,
            now,
            settings.prefetch_grace_hours,
        )
        for item in items
        if item
    }
