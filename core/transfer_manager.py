"""rclone RC integration and transfer queue management.

Transfers are stored in PostgreSQL. An asyncio background loop
picks them off the queue and executes them via rclone RC.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.ws import broadcast
from config import settings
from models.database import async_session_factory
from models.tables import MediaItem, Transfer

logger = logging.getLogger(__name__)

# Background task handle
_worker_task: asyncio.Task | None = None
_paused: bool = False

# Only these extensions are allowed to be transferred.
# Protects against accidentally syncing backup files, configs, etc.
_MEDIA_EXTENSIONS = frozenset({
    ".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".ts", ".m2ts",
    ".flac", ".mp3", ".aac", ".m4a", ".opus",
    ".srt", ".ass", ".sub", ".idx",
})


def is_paused() -> bool:
    return _paused


class TransferManager:
    """Thin facade so deps.py can hold a typed singleton reference.
    All actual logic lives in the module-level functions below."""
    pass


# ── Public API ────────────────────────────────────────────────────────────────

async def queue_transfer(
    db: AsyncSession,
    media_item_id: uuid.UUID,
    direction: str,
    trigger: str,
    priority: int = 50,
) -> Transfer:
    """Insert a transfer record and return it. Caller must commit."""
    item_result = await db.execute(select(MediaItem).where(MediaItem.id == media_item_id))
    item = item_result.scalar_one()

    # Store path relative to jellyfin_media_root — this matches the
    # subdirectory layout on both NAS and cloud remote.
    rel_path = os.path.relpath(item.file_path, settings.jellyfin_media_root)

    transfer = Transfer(
        media_item_id=media_item_id,
        direction=direction,
        trigger=trigger,
        priority=priority,
        status="queued",
        source_path=rel_path,
        dest_path=rel_path,
    )
    db.add(transfer)
    await db.flush()
    return transfer


async def stop_rclone_job(job_id: int | None) -> None:
    """Tell rclone RC to stop a job. Best-effort — logs on failure."""
    if not job_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{settings.rclone_rc_url}/job/stop", json={"jobid": job_id})
    except Exception as exc:
        logger.warning("Could not stop rclone job %s: %s", job_id, exc)


async def pause_all_transfers(db: AsyncSession) -> int:
    """Stop all active rclone jobs and re-queue their transfers. Returns count."""
    global _paused
    _paused = True

    result = await db.execute(select(Transfer).where(Transfer.status == "active"))
    active = list(result.scalars())

    for t in active:
        await stop_rclone_job(t.rclone_job_id)
        t.status = "queued"
        t.rclone_job_id = None
        t.rclone_group = None
        t.started_at = None

    # Also reset media item tier for affected items
    for t in active:
        item_result = await db.execute(select(MediaItem).where(MediaItem.id == t.media_item_id))
        item = item_result.scalar_one_or_none()
        if item:
            item.storage_tier = "hot" if t.direction == "freeze" else "cold"
            item.transfer_direction = None

    await db.commit()
    logger.info("Paused: stopped %d active transfers", len(active))
    return len(active)


def resume_transfers() -> None:
    global _paused
    _paused = False
    logger.info("Transfer worker resumed")


# ── Worker loop ───────────────────────────────────────────────────────────────

async def start_worker() -> None:
    global _worker_task
    _worker_task = asyncio.create_task(_transfer_loop(), name="transfer-worker")
    logger.info("Transfer worker started")


async def stop_worker() -> None:
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass


async def _transfer_loop() -> None:
    while True:
        try:
            await _process_queue()
        except Exception:
            logger.exception("Transfer loop error")
        await asyncio.sleep(5)


async def _process_queue() -> None:
    async with async_session_factory() as db:
        # Count active transfers by direction
        active_result = await db.execute(
            select(Transfer).where(Transfer.status == "active")
        )
        active = list(active_result.scalars())
        active_reheats = sum(1 for t in active if t.direction == "reheat")
        active_freezes = sum(1 for t in active if t.direction == "freeze")

        # Poll progress on active transfers
        for t in active:
            await _poll_transfer(db, t)

        # Pick next queued transfer (skip if globally paused).
        # Read limits from settings so UI changes take effect immediately.
        if not _paused:
            if active_reheats < settings.max_concurrent_reheats:
                await _start_next(db, "reheat")
            if active_freezes < settings.max_concurrent_freezes:
                if _freeze_window_active():
                    await _start_next(db, "freeze")

        await db.commit()


def _freeze_window_active() -> bool:
    from datetime import timezone
    import zoneinfo
    ist = zoneinfo.ZoneInfo("Asia/Kolkata")
    hour = datetime.now(tz=ist).hour
    return settings.freeze_window_start <= hour < settings.freeze_window_end


async def _start_next(db: AsyncSession, direction: str) -> None:
    result = await db.execute(
        select(Transfer)
        .where(Transfer.status == "queued", Transfer.direction == direction)
        .order_by(Transfer.priority.desc(), Transfer.queued_at.asc(), Transfer.id.asc())
        .limit(1)
    )
    transfer = result.scalar_one_or_none()
    if transfer:
        await _execute_transfer(db, transfer)


async def _execute_transfer(db: AsyncSession, transfer: Transfer) -> None:
    item_result = await db.execute(select(MediaItem).where(MediaItem.id == transfer.media_item_id))
    item = item_result.scalar_one()

    rel_path = transfer.source_path

    # Normalise: old transfers stored the full Jellyfin path (/media_2/...).
    # Strip the jellyfin_media_root prefix so we always work with a relative path.
    if os.path.isabs(rel_path):
        rel_path = os.path.relpath(rel_path, settings.jellyfin_media_root)
        # Persist the corrected path so this item never needs fixing again
        transfer.source_path = rel_path
        transfer.dest_path = rel_path

    # ── Pre-flight guard 1: media extension ──────────────────────────────────
    ext = os.path.splitext(rel_path)[1].lower()
    if ext not in _MEDIA_EXTENSIONS:
        transfer.status = "failed"
        transfer.error_message = f"Blocked: '{ext}' is not a permitted media extension"
        logger.error("Blocked transfer %s: not a media file (%s)", transfer.id, rel_path)
        return

    # ── Pre-flight guard 2: source file must exist ────────────────────────────
    if transfer.direction == "freeze":
        src_fs = f"{settings.nas_root}/"
        dst_fs = f"{settings.rclone_remote}:"
        nas_path = os.path.join(settings.nas_root, rel_path)
        if not os.path.isfile(nas_path):
            transfer.status = "failed"
            transfer.error_message = f"Source file not found on NAS: {nas_path}"
            logger.error("Transfer %s: file missing on NAS: %s", transfer.id, nas_path)
            return
    else:
        src_fs = f"{settings.rclone_remote}:"
        dst_fs = f"{settings.nas_root}/"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # operations/copyfile transfers exactly one file.
            # srcRemote / dstRemote are paths *within* their respective fs roots.
            # Never use sync/copy here — it syncs the entire srcFs if srcRemote is wrong.
            resp = await client.post(f"{settings.rclone_rc_url}/operations/copyfile", json={
                "srcFs": src_fs,
                "srcRemote": rel_path,
                "dstFs": dst_fs,
                "dstRemote": rel_path,
                "_async": True,
                "_group": f"frostbite-{transfer.id}",
            })
            resp.raise_for_status()
            job = resp.json()

        transfer.rclone_job_id = job.get("jobid")
        transfer.rclone_group = f"frostbite-{transfer.id}"
        transfer.status = "active"
        transfer.started_at = datetime.utcnow()

        item.storage_tier = "transferring"
        item.transfer_direction = transfer.direction

        logger.info("Started %s for %s (job=%s)", transfer.direction, item.title, transfer.rclone_job_id)
        await broadcast({"type": "transfer_start", "transfer_id": str(transfer.id), "title": item.title})

    except Exception as exc:
        logger.error("Failed to start transfer %s: %s", transfer.id, exc)
        transfer.status = "failed"
        transfer.error_message = str(exc)


async def _poll_transfer(db: AsyncSession, transfer: Transfer) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(f"{settings.rclone_rc_url}/core/stats", json={
                "group": transfer.rclone_group
            })
            stats = resp.json()
    except Exception as exc:
        logger.warning("Failed to poll transfer %s: %s", transfer.id, exc)
        return

    transfer.bytes_transferred = stats.get("bytes", 0)
    transfer.bytes_total = stats.get("totalBytes", 0)
    transfer.speed_bps = int(stats.get("speed", 0))
    transfer.eta_seconds = stats.get("eta")

    # Check if the rclone job finished
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(f"{settings.rclone_rc_url}/job/status", json={
                "jobid": transfer.rclone_job_id
            })
            job_status = resp.json()
    except Exception:
        return

    if job_status.get("finished"):
        if job_status.get("error"):
            transfer.status = "failed"
            transfer.error_message = job_status["error"]
            logger.error("Transfer %s failed: %s", transfer.id, transfer.error_message)
        else:
            transfer.status = "completed"
            transfer.completed_at = datetime.utcnow()
            await _on_transfer_complete(db, transfer)

    await broadcast({
        "type": "transfer_progress",
        "transfer_id": str(transfer.id),
        "bytes_transferred": transfer.bytes_transferred,
        "bytes_total": transfer.bytes_total,
        "speed_bps": transfer.speed_bps,
        "eta_seconds": transfer.eta_seconds,
    })


async def _verify_cloud_copy(file_path: str, expected_size: int) -> bool:
    """
    Confirm the file exists on the cloud remote and its size matches.
    Uses rclone RC operations/stat against the transfer daemon (5572).
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{settings.rclone_rc_url}/operations/stat", json={
                "fs": f"{settings.rclone_remote}:",
                "remote": file_path,
            })
            if resp.status_code != 200:
                return False
            stat = resp.json()
            remote_size = stat.get("item", {}).get("Size", -1)
            if expected_size > 0 and remote_size != expected_size:
                logger.warning(
                    "Size mismatch for %s: NAS=%d cloud=%d", file_path, expected_size, remote_size
                )
                return False
            return True
    except Exception as exc:
        logger.warning("Cloud verification failed for %s: %s", file_path, exc)
        return False


async def _delete_nas_copy(file_path: str) -> bool:
    """
    Delete the NAS copy of a file after a successful freeze + verification.
    Uses rclone RC so we stay consistent — no direct os.remove().
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{settings.rclone_rc_url}/operations/deletefile", json={
                "fs": f"{settings.nas_root}/",
                "remote": file_path,
            })
            resp.raise_for_status()
            logger.info("Deleted NAS copy: %s", file_path)
            return True
    except Exception as exc:
        logger.error("Failed to delete NAS copy of %s: %s", file_path, exc)
        return False


async def _on_transfer_complete(db: AsyncSession, transfer: Transfer) -> None:
    item_result = await db.execute(select(MediaItem).where(MediaItem.id == transfer.media_item_id))
    item = item_result.scalar_one()

    if transfer.direction == "freeze":
        # Verify the cloud copy exists and size matches before deleting from NAS
        verified = await _verify_cloud_copy(transfer.dest_path, item.file_size_bytes)
        if not verified:
            transfer.status = "failed"
            transfer.error_message = "Cloud verification failed — NAS copy retained"
            item.storage_tier = "hot"
            item.transfer_direction = None
            logger.error("Freeze verification failed for %s — NAS copy kept", item.title)
            await broadcast({
                "type": "transfer_failed",
                "transfer_id": str(transfer.id),
                "title": item.title,
                "reason": "cloud_verification_failed",
            })
            return

        # Verified — safe to delete NAS copy
        deleted = await _delete_nas_copy(transfer.source_path)
        if not deleted:
            # Cloud copy is there but we couldn't delete NAS — not fatal,
            # mark as cold anyway (mergerfs will prefer NAS copy on reads which is fine)
            logger.warning("Could not delete NAS copy of %s, marking cold anyway", item.title)

        new_tier = "cold"

    else:
        # Reheat — file is now on NAS, cloud copy stays as backup
        new_tier = "hot"

    item.storage_tier = new_tier
    item.transfer_direction = None

    # Invalidate rclone VFS cache on ALL nodes that mount the cloud remote.
    # vfs/refresh only works on directories already in the VFS cache. If the
    # immediate parent hasn't been listed yet, rclone returns HTTP 200 with
    # {"result": {"dir": "file does not exist"}}. In that case we walk up to
    # the grandparent (series dir) which is always cached, then retry.
    parts = transfer.dest_path.split("/")
    parent_dir = "/".join(parts[:-1])        # e.g. series/anime/Show/Season 4
    grandparent_dir = "/".join(parts[:-2])   # e.g. series/anime/Show

    vfs_urls = [u.strip() for u in settings.rclone_vfs_urls.split(",") if u.strip()]
    async with httpx.AsyncClient(timeout=10) as client:
        for vfs_url in vfs_urls:
            try:
                resp = await client.post(f"{vfs_url}/vfs/refresh", json={"dir": parent_dir})
                body = resp.json()
                # If rclone doesn't have a cache entry for this dir, refresh the
                # grandparent first so it discovers the season directory, then retry.
                if any("does not exist" in str(v) for v in body.get("result", {}).values()):
                    logger.debug("VFS refresh: %s not cached on %s, refreshing grandparent", parent_dir, vfs_url)
                    await client.post(f"{vfs_url}/vfs/refresh", json={"dir": grandparent_dir})
                    await client.post(f"{vfs_url}/vfs/refresh", json={"dir": parent_dir})
            except Exception as exc:
                logger.warning("VFS cache refresh failed for %s: %s", vfs_url, exc)

    logger.info("Transfer complete: %s is now %s", item.title, new_tier)
    await broadcast({"type": "transfer_complete", "transfer_id": str(transfer.id), "title": item.title, "tier": new_tier})
