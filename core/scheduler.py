"""APScheduler periodic tasks."""

import logging
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select, text

from config import settings
from core.filesystem import nas_free_bytes
from core.tdarr_client import TdarrClient
from core.playback_import import sync_playback_from_reporting
from core.transfer_manager import queue_transfer, start_worker, stop_worker
from models.database import async_session_factory
from models.tables import MediaItem, ScoreHistory, Transfer

logger = logging.getLogger(__name__)
_scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


async def start_scheduler() -> None:
    _scheduler.add_job(sync_tdarr_eligibility, "interval", minutes=10, id="tdarr_sync")
    _scheduler.add_job(sync_playback_from_reporting, "interval", minutes=5, id="playback_sync")
    _scheduler.add_job(scoring_sweep, "interval", minutes=15, id="scoring_sweep")
    _scheduler.add_job(check_nas_space, "interval", minutes=5, id="nas_space")
    _scheduler.add_job(cleanup_stale_transfers, "interval", hours=1, id="stale_cleanup")
    _scheduler.add_job(record_score_snapshot, "interval", minutes=30, id="score_snapshot")
    _scheduler.add_job(scheduled_library_sync, "cron", hour=3, minute=0, id="library_sync")
    _scheduler.start()
    await start_worker()
    logger.info("Scheduler started")


async def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
    await stop_worker()


# ── Tasks ─────────────────────────────────────────────────────────────────────

async def sync_tdarr_eligibility() -> None:
    """
    Ask Tdarr for all files it considers done (AV1 encode complete or not required).
    Flip tdarr_eligible=True on matching media_items so they enter the scoring cycle.
    Runs every 10 minutes.
    """
    client = TdarrClient()
    eligible_files = await client.get_eligible_files()
    if not eligible_files:
        return

    # Build a set of absolute paths Tdarr says are done.
    # Tdarr uses file path as the document _id; "file" field may also be present.
    done_paths: set[str] = {
        f.get("_id") or f.get("file")
        for f in eligible_files
        if f.get("_id") or f.get("file")
    }

    async with async_session_factory() as db:
        result = await db.execute(
            select(MediaItem).where(MediaItem.tdarr_eligible == False)  # noqa: E712
        )
        newly_eligible = 0
        for item in result.scalars():
            # file_path uses Jellyfin's internal prefix (e.g. /media_2/...).
            # Tdarr may use a different mount — try exact match first,
            # then suffix match on the relative portion.
            match = item.file_path in done_paths
            if not match:
                try:
                    rel = os.path.relpath(item.file_path, settings.jellyfin_media_root)
                    match = any(p.endswith(rel) for p in done_paths)
                except ValueError:
                    pass
            if match:
                item.tdarr_eligible = True
                item.tdarr_status = "done"
                newly_eligible += 1

        if newly_eligible:
            await db.commit()
            logger.info("Tdarr sync: %d items newly eligible for scoring", newly_eligible)


async def scoring_sweep() -> None:
    """Rescore all items and queue freeze/reheat candidates."""
    from core.scorer import ItemMeta, PlaybackStats, calculate_temperature

    async with async_session_factory() as db:
        # Only score tdarr-eligible items — Tdarr must confirm a file is in its
        # final encoded form before Frostbite decides its temperature and whether
        # to freeze it. Non-eligible items keep temperature=100 (always hot).
        result = await db.execute(
            select(MediaItem).where(MediaItem.tdarr_eligible == True)  # noqa: E712
        )
        items = list(result.scalars())
        logger.info("Scoring sweep: %d tdarr-eligible items to score", len(items))

        # Fetch all pending transfers keyed by media_item_id so we can both
        # avoid duplicates AND cancel stale transfers when scores change.
        pending_result = await db.execute(
            select(Transfer).where(Transfer.status.in_(["queued", "active"]))
        )
        # dict: media_item_id -> list[Transfer]
        pending_by_item: dict = {}
        for t in pending_result.scalars():
            pending_by_item.setdefault(t.media_item_id, []).append(t)

        queued_freeze = queued_reheat = cancelled_stale = 0
        for item in items:
            # Fetch stats from the materialized view if available, otherwise use zeros
            stats_row = None
            try:
                stats_result = await db.execute(
                    text("SELECT * FROM item_playback_stats WHERE media_item_id = :id"),
                    {"id": item.id},
                )
                stats_row = stats_result.mappings().one_or_none()
            except Exception:
                pass

            stats = PlaybackStats(
                last_played_at=stats_row["last_played_at"] if stats_row else None,
                total_plays=stats_row["total_plays"] if stats_row else 0,
                unique_viewers=stats_row["unique_viewers"] if stats_row else 0,
                plays_last_7d=stats_row["plays_last_7d"] if stats_row else 0,
                plays_last_30d=stats_row["plays_last_30d"] if stats_row else 0,
            )
            meta = ItemMeta(
                file_size_bytes=item.file_size_bytes,
                date_added=item.date_added,
                series_status=item.series_status,
                community_rating=item.community_rating,
            )
            new_temp = calculate_temperature(meta, stats)
            item.temperature = new_temp
            item.last_scored_at = datetime.utcnow()

            existing = pending_by_item.get(item.id, [])

            # Cancel stale QUEUED (not active) transfers whose direction no
            # longer makes sense after rescoring.
            for t in list(existing):
                if t.status != "queued":
                    continue
                if t.direction == "freeze" and new_temp >= settings.freeze_threshold:
                    t.status = "cancelled"
                    existing.remove(t)
                    cancelled_stale += 1
                elif t.direction == "reheat" and new_temp <= settings.reheat_threshold:
                    t.status = "cancelled"
                    existing.remove(t)
                    cancelled_stale += 1

            # Skip if still has a live pending transfer after cleanup
            if existing:
                continue

            if item.storage_tier == "hot" and new_temp < settings.freeze_threshold:
                await queue_transfer(db, item.id, "freeze", "auto_score", priority=int(settings.freeze_threshold - new_temp))
                pending_by_item[item.id] = [True]  # sentinel — prevents double-queue
                queued_freeze += 1
            elif item.storage_tier == "cold" and new_temp > settings.reheat_threshold:
                await queue_transfer(db, item.id, "reheat", "auto_score", priority=int(new_temp - settings.reheat_threshold))
                pending_by_item[item.id] = [True]
                queued_reheat += 1

        await db.commit()
        logger.info(
            "Scoring sweep complete: %d rescored, +%d freeze / +%d reheat queued, %d stale cancelled",
            len(items), queued_freeze, queued_reheat, cancelled_stale,
        )


async def check_nas_space() -> None:
    """Trigger emergency freezes if NAS free space drops below threshold."""
    free_gb = nas_free_bytes() / (1024 ** 3)
    if free_gb < settings.emergency_freeze_threshold_gb:
        logger.warning("NAS free space critical: %.1f GB — triggering emergency freezes", free_gb)
        async with async_session_factory() as db:
            result = await db.execute(
                select(MediaItem)
                .where(MediaItem.storage_tier == "hot")
                .order_by(MediaItem.temperature.asc())
                .limit(10)
            )
            for item in result.scalars():
                await queue_transfer(db, item.id, "freeze", "space_pressure", priority=95)
            await db.commit()


async def cleanup_stale_transfers() -> None:
    """Mark transfers that have been active for >2 hours as failed."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=2)
    async with async_session_factory() as db:
        result = await db.execute(
            select(Transfer).where(Transfer.status == "active", Transfer.started_at < cutoff)
        )
        stale = list(result.scalars())
        for t in stale:
            t.status = "failed"
            t.error_message = "Transfer timed out (stale cleanup)"
            # Reset item tier
            item_result = await db.execute(select(MediaItem).where(MediaItem.id == t.media_item_id))
            item = item_result.scalar_one_or_none()
            if item:
                item.storage_tier = "hot" if t.direction == "freeze" else "cold"
                item.transfer_direction = None
        if stale:
            logger.warning("Cleaned up %d stale transfers", len(stale))
        await db.commit()


async def scheduled_library_sync() -> None:
    """Daily library sync at 3:00 IST — walk filesystem and upsert into media_items."""
    from core.library_sync import run_library_sync
    await run_library_sync()  # scheduler already runs in the background


async def record_score_snapshot() -> None:
    """Record an aggregate snapshot for dashboard historical charts."""
    async with async_session_factory() as db:
        from sqlalchemy import case
        result = await db.execute(
            select(
                func.count().label("total"),
                func.sum(case((MediaItem.storage_tier == "hot", 1), else_=0)).label("hot"),
                func.sum(case((MediaItem.storage_tier == "cold", 1), else_=0)).label("cold"),
                func.avg(MediaItem.temperature).label("avg_temp"),
            )
        )
        row = result.one()

        nas_used = 0
        try:
            sv = os.statvfs(settings.nas_root)
            total_bytes = sv.f_blocks * sv.f_frsize
            free_bytes = sv.f_bavail * sv.f_frsize
            nas_used = total_bytes - free_bytes
        except OSError:
            pass

        cloud_used = 0
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{settings.rclone_rc_url}/operations/about",
                    json={"fs": f"{settings.rclone_remote}:"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    cloud_used = data.get("used", 0) or 0
                    logger.info("Cloud usage: %.1f GB (raw: %s)", cloud_used / 1e9, data)
                else:
                    logger.warning(
                        "operations/about returned %d: %s", resp.status_code, resp.text[:200]
                    )
        except Exception as exc:
            logger.warning("Could not fetch cloud usage from rclone: %s", exc)

        db.add(ScoreHistory(
            total_items=row.total or 0,
            hot_items=row.hot or 0,
            cold_items=row.cold or 0,
            nas_used_bytes=nas_used,
            cloud_used_bytes=cloud_used,
            avg_temperature=float(row.avg_temp or 0),
        ))
        await db.commit()
