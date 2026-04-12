"""Predictive prefetch engine + playback event handlers.

Entry points called by the webhook route:
    on_playback_start(event)
    on_playback_stop(event)
    on_playback_progress(event)
    on_item_added(payload)
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.ws import broadcast
from config import settings
from core.transfer_manager import queue_transfer
from models.database import async_session_factory
from models.schemas import PlaybackEventIn
from models.tables import MediaItem, PlaybackEvent

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_create_item(db: AsyncSession, event: PlaybackEventIn) -> MediaItem | None:
    # Primary lookup by jellyfin_id (strip hyphens — webhook sends UUID format,
    # library sync stores bare hex)
    normalized_id = event.jellyfin_id.replace("-", "")
    result = await db.execute(
        select(MediaItem).where(MediaItem.jellyfin_id == normalized_id)
    )
    item = result.scalar_one_or_none()
    if item:
        return item

    # Fallback: Jellyfin webhook may send a different ID format than the Items API.
    # Try matching by file_path instead.
    if event.file_path:
        result = await db.execute(
            select(MediaItem).where(MediaItem.file_path == event.file_path)
        )
        item = result.scalar_one_or_none()
        if item:
            logger.info(
                "Matched item by file_path (webhook id %s != db id %s): %s",
                event.jellyfin_id, item.jellyfin_id, item.title,
            )
            return item

    if not event.file_path or not event.item_type:
        return None

    item = MediaItem(
        jellyfin_id=event.jellyfin_id,
        title=event.title or event.jellyfin_id,
        item_type=event.item_type,
        series_id=event.series_id,
        series_name=event.series_name,
        season_number=event.season_number,
        episode_number=event.episode_number,
        file_path=event.file_path,
        file_size_bytes=0,  # will be updated by library sync
        storage_tier="hot",
        temperature=100.0,
    )
    db.add(item)
    await db.flush()
    return item


async def _record_event(db: AsyncSession, item: MediaItem, event: PlaybackEventIn) -> None:
    db.add(PlaybackEvent(
        media_item_id=item.id,
        user_id=event.user_id,
        username=event.username,
        event_type=event.event_type,
        play_method=event.play_method,
        position_ticks=event.position_ticks,
        duration_ticks=event.duration_ticks,
        client_name=event.client_name,
        device_name=event.device_name,
    ))


async def _boost_temperature(db: AsyncSession, item: MediaItem, boost: float) -> None:
    item.temperature = min(100.0, item.temperature + boost)
    item.last_scored_at = datetime.utcnow()


async def _prefetch_next_episodes(db: AsyncSession, item: MediaItem) -> None:
    if not item.series_id or item.episode_number is None:
        return

    now = datetime.utcnow()
    cooldown_cutoff = now - timedelta(days=settings.prefetch_cooldown_days)

    result = await db.execute(
        select(MediaItem)
        .where(
            MediaItem.series_id == item.series_id,
            MediaItem.season_number == item.season_number,
            MediaItem.episode_number > item.episode_number,
            MediaItem.episode_number <= item.episode_number + 3,
        )
        .order_by(MediaItem.episode_number)
    )
    for i, ep in enumerate(result.scalars()):
        recently_prefetched = ep.last_prefetch_at and ep.last_prefetch_at > cooldown_cutoff
        # Always reheat cold episodes — cooldown only gates the temp boost
        # (prevents ping-pong on episodes that stay hot after prefetch)
        if not recently_prefetched:
            await _boost_temperature(db, ep, settings.prefetch_boost)
            ep.last_prefetch_at = now
        if ep.storage_tier == "cold":
            priority = 90 - (i * 10)
            ep.last_prefetch_at = now
            await queue_transfer(db, ep.id, direction="reheat", trigger="prefetch", priority=priority)

    # Season boundary look-ahead
    total_result = await db.execute(
        select(MediaItem).where(
            MediaItem.series_id == item.series_id,
            MediaItem.season_number == item.season_number,
        )
    )
    total_in_season = len(list(total_result.scalars()))
    if item.episode_number >= total_in_season - 1:
        premiere_result = await db.execute(
            select(MediaItem).where(
                MediaItem.series_id == item.series_id,
                MediaItem.season_number == (item.season_number or 0) + 1,
                MediaItem.episode_number == 1,
            )
        )
        premiere = premiere_result.scalar_one_or_none()
        if premiere and premiere.storage_tier == "cold":
            if not premiere.last_prefetch_at or premiere.last_prefetch_at <= cooldown_cutoff:
                premiere.last_prefetch_at = now
                await queue_transfer(db, premiere.id, direction="reheat", trigger="prefetch", priority=75)


# ── Public handlers ───────────────────────────────────────────────────────────

async def on_playback_start(event: PlaybackEventIn) -> None:
    async with async_session_factory() as db:
        item = await _get_or_create_item(db, event)
        if not item:
            logger.warning("PlaybackStart: could not find/create item %s", event.jellyfin_id)
            return

        await _record_event(db, item, event)
        await _boost_temperature(db, item, 30.0)

        if item.item_type == "episode":
            await _prefetch_next_episodes(db, item)

        await db.commit()
        await broadcast({"type": "score_update", "jellyfin_id": item.jellyfin_id, "temperature": item.temperature})
        logger.info("PlaybackStart: %s (tier=%s, temp=%.1f)", item.title, item.storage_tier, item.temperature)


async def on_playback_stop(event: PlaybackEventIn) -> None:
    async with async_session_factory() as db:
        item = await _get_or_create_item(db, event)
        if not item:
            return

        await _record_event(db, item, event)

        # Extra boost if they watched most of it (>80%)
        if event.position_ticks and event.duration_ticks and event.duration_ticks > 0:
            completion = event.position_ticks / event.duration_ticks
            if completion >= 0.8:
                await _boost_temperature(db, item, 10.0)

        await db.commit()
        await broadcast({"type": "score_update", "jellyfin_id": item.jellyfin_id, "temperature": item.temperature})


async def on_playback_progress(event: PlaybackEventIn) -> None:
    async with async_session_factory() as db:
        item = await _get_or_create_item(db, event)
        if not item:
            return
        await _record_event(db, item, event)

        # Progress-as-Start fallback: native clients (Findroid, Swiftfin, etc.)
        # often don't send PlaybackStart webhooks at all — only Progress ticks.
        # If we haven't seen a real start event in the last 30 minutes for this
        # item, treat this progress as a start and trigger prefetch.
        if item.item_type == "episode":
            recent_start = await db.execute(
                select(PlaybackEvent)
                .where(
                    PlaybackEvent.media_item_id == item.id,
                    PlaybackEvent.event_type == "start",
                    PlaybackEvent.created_at > datetime.utcnow() - timedelta(minutes=30),
                )
                .limit(1)
            )
            if not recent_start.scalar_one_or_none():
                logger.info("Progress-as-Start fallback for %s (no recent start event)", item.title)
                # Record a synthetic start so subsequent progress ticks don't re-trigger
                db.add(PlaybackEvent(
                    media_item_id=item.id,
                    user_id=event.user_id or "",
                    username=event.username,
                    event_type="start",
                    play_method=event.play_method,
                    client_name=event.client_name,
                    device_name=event.device_name,
                ))
                await _boost_temperature(db, item, 30.0)
                await _prefetch_next_episodes(db, item)

        await db.commit()


async def on_item_added(payload: dict) -> None:
    item_data = payload.get("Item") or {}
    jellyfin_id = item_data.get("Id")
    if not jellyfin_id:
        return

    async with async_session_factory() as db:
        result = await db.execute(select(MediaItem).where(MediaItem.jellyfin_id == jellyfin_id))
        if result.scalar_one_or_none():
            return  # Already known

        sources = item_data.get("MediaSources") or []
        file_path = sources[0].get("Path") if sources else item_data.get("Path", "")
        size = sources[0].get("Size", 0) if sources else 0

        item = MediaItem(
            jellyfin_id=jellyfin_id,
            title=item_data.get("Name", jellyfin_id),
            item_type=(item_data.get("Type") or "unknown").lower(),
            series_id=item_data.get("SeriesId"),
            series_name=item_data.get("SeriesName"),
            season_number=item_data.get("ParentIndexNumber"),
            episode_number=item_data.get("IndexNumber"),
            file_path=file_path,
            file_size_bytes=size,
            storage_tier="hot",
            temperature=100.0,
            date_added=datetime.utcnow(),
        )
        db.add(item)
        await db.commit()
        logger.info("ItemAdded: %s (%s)", item.title, jellyfin_id)
