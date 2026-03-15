"""APScheduler periodic tasks."""

import logging
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select, text

from config import settings
from core.filesystem import nas_free_bytes
from core.tdarr_client import TdarrClient
from core.transfer_manager import queue_transfer, start_worker, stop_worker
from models.database import async_session_factory
from models.tables import MediaItem, ScoreHistory, Transfer

logger = logging.getLogger(__name__)
_scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


async def start_scheduler() -> None:
    _scheduler.add_job(sync_tdarr_eligibility, "interval", minutes=10, id="tdarr_sync")
    _scheduler.add_job(refresh_playback_stats, "interval", minutes=5, id="refresh_stats")
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

    # Build a set of absolute paths Tdarr says are done
    done_paths: set[str] = {f["file"] for f in eligible_files if f.get("file")}

    async with async_session_factory() as db:
        result = await db.execute(
            select(MediaItem).where(MediaItem.tdarr_eligible == False)  # noqa: E712
        )
        newly_eligible = 0
        for item in result.scalars():
            # file_path is absolute (e.g. /mnt/merged/media/...).
            # Tdarr may use a different mount — fall back to suffix matching.
            match = item.file_path in done_paths
            if not match:
                try:
                    rel = os.path.relpath(item.file_path, settings.media_root)
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

async def refresh_playback_stats() -> None:
    """Refresh the item_playback_stats materialized view."""
    async with async_session_factory() as db:
        try:
            await db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY item_playback_stats"))
            await db.commit()
        except Exception as exc:
            logger.warning("Failed to refresh playback stats: %s", exc)


async def scoring_sweep() -> None:
    """Rescore all items and queue freeze/reheat candidates."""
    from core.scorer import ItemMeta, PlaybackStats, calculate_temperature

    async with async_session_factory() as db:
        result = await db.execute(
            select(MediaItem).where(MediaItem.tdarr_eligible == True)  # noqa: E712
        )
        items = list(result.scalars())

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

            # Queue transfers based on thresholds
            if item.storage_tier == "hot" and new_temp < settings.freeze_threshold:
                await queue_transfer(db, item.id, "freeze", "auto_score", priority=int(settings.freeze_threshold - new_temp))
            elif item.storage_tier == "cold" and new_temp > settings.reheat_threshold:
                await queue_transfer(db, item.id, "reheat", "auto_score", priority=int(new_temp - settings.reheat_threshold))

        await db.commit()
        logger.info("Scoring sweep complete: %d items rescored", len(items))


async def check_nas_space() -> None:
    """Trigger emergency freezes if NAS free space drops below threshold."""
    free_gb = nas_free_bytes() / (1024 ** 3)
    if free_gb < settings.emergency_freeze_threshold_gb:
        logger.warning("NAS free space critical: %.1f GB — triggering emergency freezes", free_gb)
        async with async_session_factory() as db:
            result = await db.execute(
                select(MediaItem)
                .where(
                    MediaItem.storage_tier == "hot",
                    MediaItem.tdarr_eligible == True,  # noqa: E712
                )
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
    await run_library_sync()


async def record_score_snapshot() -> None:
    """Record an aggregate snapshot for dashboard historical charts."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(
                func.count().label("total"),
                func.sum((MediaItem.storage_tier == "hot").cast("integer")).label("hot"),
                func.sum((MediaItem.storage_tier == "cold").cast("integer")).label("cold"),
                func.avg(MediaItem.temperature).label("avg_temp"),
            )
        )
        row = result.one()

        nas_used = 0
        try:
            sv = os.statvfs(settings.nas_root)
            total = sv.f_blocks * sv.f_frsize
            free = sv.f_bavail * sv.f_frsize
            nas_used = total - free
        except OSError:
            pass

        db.add(ScoreHistory(
            total_items=row.total or 0,
            hot_items=row.hot or 0,
            cold_items=row.cold or 0,
            nas_used_bytes=nas_used,
            cloud_used_bytes=0,  # rclone about would give this — future enhancement
            avg_temperature=float(row.avg_temp or 0),
        ))
        await db.commit()
