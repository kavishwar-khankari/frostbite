"""Deletion candidate scanning, approval, protection, and notification.

Deletion is always approval-gated:
1. Scheduler scans cold items below the deletion threshold.
2. Pending candidates appear in the Preserve page.
3. User approves or protects each candidate.
4. On approval, the cloud file is deleted via rclone RC.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.ws import broadcast
from config import settings
from core.filesystem import bytes_to_gib
from models.database import async_session_factory
from models.tables import (
    DeletionCandidate,
    DeletionException,
    MediaItem,
    Transfer,
)

logger = logging.getLogger(__name__)


def _relative_media_path(file_path: str) -> str:
    try:
        return os.path.relpath(file_path, settings.jellyfin_media_root)
    except ValueError:
        return file_path


def _nas_path(file_path: str) -> str:
    rel = _relative_media_path(file_path)
    return os.path.join(settings.nas_root, rel)


async def _cloud_file_exists(rel_path: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{settings.rclone_rc_url}/operations/stat", json={
                "fs": f"{settings.rclone_remote}:",
                "remote": rel_path,
            })
            if resp.status_code != 200:
                return False
            return resp.json().get("item") is not None
    except Exception:
        return False


async def _delete_cloud_file(rel_path: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{settings.rclone_rc_url}/operations/deletefile", json={
            "fs": f"{settings.rclone_remote}:",
            "remote": rel_path,
        })
        resp.raise_for_status()


async def _verify_cloud_deleted(rel_path: str) -> bool:
    exists = await _cloud_file_exists(rel_path)
    return not exists


async def _invalidate_vfs(rel_path: str) -> None:
    parts = rel_path.split("/")
    parent_dir = "/".join(parts[:-1])
    grandparent_dir = "/".join(parts[:-2])

    vfs_urls = [u.strip() for u in settings.rclone_vfs_urls.split(",") if u.strip()]
    async with httpx.AsyncClient(timeout=10) as client:
        for vfs_url in vfs_urls:
            try:
                await client.post(f"{vfs_url}/vfs/forget", json={"file": rel_path})
                await client.post(f"{vfs_url}/vfs/refresh", json={"dir": parent_dir})
            except Exception:
                try:
                    await client.post(f"{vfs_url}/vfs/refresh", json={"dir": grandparent_dir})
                    await client.post(f"{vfs_url}/vfs/refresh", json={"dir": parent_dir})
                except Exception as exc:
                    logger.warning("VFS invalidate failed for %s on %s: %s", rel_path, vfs_url, exc)


async def _send_deletion_notification(candidate_data: list[dict]) -> None:
    if not settings.deletion_notifications_enabled or not candidate_data:
        return

    if not settings.apprise_config_key:
        logger.warning("Apprise config key not set — skipping notification")
        return

    url = f"{settings.apprise_url.rstrip('/')}/notify/{settings.apprise_config_key}"

    top = candidate_data[:10]
    lines = [f"{len(candidate_data)} cold media items are below deletion threshold {settings.deletion_threshold}."]
    lines.append(f"Review them: {settings.frostbite_public_url.rstrip('/')}/preserve")
    lines.append("")
    lines.append("Top candidates:")
    for d in top:
        name = d["title"]
        if d.get("season_number") is not None and d.get("episode_number") is not None:
            name = f"{d['series_name'] or d['series_id']} S{d['season_number']:02d}E{d['episode_number']:02d}"
        size_gib = bytes_to_gib(d["file_size_bytes"]) or 0.0
        lines.append(f"- {name} — temp {d['temperature']} — {size_gib:.1f} GiB")

    if len(candidate_data) > 10:
        lines.append(f"... and {len(candidate_data) - 10} more")

    body = "\n".join(lines)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "title": "Frostbite: deletion approvals needed",
                "body": body,
                "type": "warning",
                "format": "markdown",
            })
            if resp.status_code >= 400:
                logger.warning("Apprise notification failed (HTTP %s): %s", resp.status_code, resp.text[:200])
                return False
    except Exception as exc:
        logger.warning("Apprise notification failed: %s", exc)
        return False
    return True


async def get_item_protection(item: MediaItem, db: AsyncSession) -> tuple[bool, str | None, uuid.UUID | None]:
    item_exc_result = await db.execute(
        select(DeletionException).where(
            DeletionException.scope == "item",
            DeletionException.jellyfin_id == item.jellyfin_id,
        )
    )
    item_exc = item_exc_result.scalar_one_or_none()
    if item_exc:
        return True, "item", item_exc.id

    if item.series_id:
        series_exc_result = await db.execute(
            select(DeletionException).where(
                DeletionException.scope == "series",
                DeletionException.series_id == item.series_id,
            )
        )
        series_exc = series_exc_result.scalar_one_or_none()
        if series_exc:
            return True, "series", series_exc.id

    return False, None, None


async def scan_deletion_candidates(db: AsyncSession | None = None) -> dict:
    own_db = db is None
    if own_db:
        db = async_session_factory()

    try:
        scanned = superseded = created = protected = notified = 0

        # ── Supersede stale pending candidates ────────────────────────────
        pending_result = await db.execute(
            select(DeletionCandidate).where(DeletionCandidate.status == "pending")
        )
        for candidate in pending_result.scalars():
            superseded += await _supersede_if_stale(db, candidate)

        # ── Find eligible media ───────────────────────────────────────────
        active_transfer_q = (
            select(Transfer.media_item_id)
            .where(Transfer.status.in_(["queued", "active"]))
        )

        item_exception_ids_q = (
            select(DeletionException.jellyfin_id)
            .where(DeletionException.scope == "item")
        )
        series_exception_ids_q = (
            select(DeletionException.series_id)
            .where(DeletionException.scope == "series")
        )

        active_candidate_ids_q = (
            select(DeletionCandidate.jellyfin_id)
            .where(DeletionCandidate.status.in_(["pending", "failed", "deleted", "protected"]))
        )

        eligible_q = (
            select(MediaItem)
            .where(
                MediaItem.storage_tier == "cold",
                MediaItem.item_type.in_(["movie", "episode"]),
                MediaItem.temperature <= settings.deletion_threshold,
                MediaItem.deleted_at.is_(None),
                MediaItem.id.not_in(active_transfer_q),
                MediaItem.jellyfin_id.not_in(item_exception_ids_q),
                MediaItem.series_id.not_in(series_exception_ids_q),
                MediaItem.jellyfin_id.not_in(active_candidate_ids_q),
            )
        )

        eligible_result = await db.execute(eligible_q)
        eligible_items = list(eligible_result.scalars())
        scanned = len(eligible_items)

        # ── Create candidates ─────────────────────────────────────────────
        new_candidates = []
        now = datetime.utcnow()
        for item in eligible_items:
            candidate = DeletionCandidate(
                media_item_id=item.id,
                jellyfin_id=item.jellyfin_id,
                title=item.title,
                item_type=item.item_type,
                series_id=item.series_id,
                series_name=item.series_name,
                season_number=item.season_number,
                episode_number=item.episode_number,
                file_path=item.file_path,
                file_size_bytes=item.file_size_bytes,
                temperature=item.temperature,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            db.add(candidate)
            new_candidates.append(candidate)
            created += 1

        if new_candidates:
            notification_data = [
                {
                    "title": c.title,
                    "season_number": c.season_number,
                    "episode_number": c.episode_number,
                    "series_name": c.series_name,
                    "series_id": c.series_id,
                    "file_size_bytes": c.file_size_bytes,
                    "temperature": c.temperature,
                }
                for c in new_candidates
            ]

        await db.commit()

        if new_candidates:
            try:
                sent = await _send_deletion_notification(notification_data)
                if sent:
                    now = datetime.utcnow()
                    for c in new_candidates:
                        c.notified_at = now
                    await db.commit()
                    notified = len(new_candidates)
                else:
                    notified = 0
            except Exception:
                logger.exception("Failed to send deletion notification")

        result = {
            "scanned": scanned,
            "created": created,
            "superseded": superseded,
            "protected": protected,
            "notified": notified,
        }
        logger.info(
            "Deletion scan: %d scanned, %d new, %d superseded, %d notified",
            scanned, created, superseded, notified,
        )
        return result

    finally:
        if own_db:
            await db.close()


async def _supersede_if_stale(db: AsyncSession, candidate: DeletionCandidate) -> int:
    item_result = await db.execute(
        select(MediaItem).where(MediaItem.jellyfin_id == candidate.jellyfin_id)
    )
    item = item_result.scalar_one_or_none()

    if item is None:
        candidate.status = "superseded"
        candidate.updated_at = datetime.utcnow()
        return 1

    if item.storage_tier != "cold":
        candidate.status = "superseded"
        candidate.updated_at = datetime.utcnow()
        return 1

    if item.temperature > settings.deletion_threshold:
        candidate.status = "superseded"
        candidate.updated_at = datetime.utcnow()
        return 1

    transfer_result = await db.execute(
        select(Transfer).where(
            Transfer.media_item_id == item.id,
            Transfer.status.in_(["queued", "active"]),
        )
    )
    if transfer_result.scalar_one_or_none():
        candidate.status = "superseded"
        candidate.updated_at = datetime.utcnow()
        return 1

    protected, scope, _exc_id = await get_item_protection(item, db)
    if protected:
        candidate.status = "protected"
        candidate.updated_at = datetime.utcnow()
        return 1

    return 0


async def approve_deletion(candidate_id: uuid.UUID, db: AsyncSession) -> DeletionCandidate:
    result = await db.execute(
        select(DeletionCandidate).where(DeletionCandidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise ValueError("Candidate not found")
    if candidate.status not in ("pending", "failed"):
        raise ValueError(f"Cannot approve candidate in status '{candidate.status}'")

    item_result = await db.execute(
        select(MediaItem).where(MediaItem.jellyfin_id == candidate.jellyfin_id)
    )
    item = item_result.scalar_one_or_none()

    if item is None:
        candidate.status = "superseded"
        candidate.updated_at = datetime.utcnow()
        await db.commit()
        raise ValueError("Media item no longer exists")

    if item.storage_tier != "cold":
        candidate.status = "superseded"
        candidate.updated_at = datetime.utcnow()
        await db.commit()
        raise ValueError("Item is no longer cold")

    if item.temperature > settings.deletion_threshold:
        raise ValueError("Item temperature now above deletion threshold")

    protected, scope, _exc_id = await get_item_protection(item, db)
    if protected:
        candidate.status = "protected"
        candidate.updated_at = datetime.utcnow()
        await db.commit()
        raise ValueError(f"Item is protected by {scope} exception")

    transfer_result = await db.execute(
        select(Transfer).where(
            Transfer.media_item_id == item.id,
            Transfer.status.in_(["queued", "active"]),
        )
    )
    if transfer_result.scalar_one_or_none():
        raise ValueError("Item has an active or queued transfer")

    nas_p = _nas_path(item.file_path)
    if os.path.isfile(nas_p):
        item.storage_tier = "hot"
        candidate.status = "superseded"
        candidate.error_message = "NAS copy exists — item is hot, not safe to delete cloud copy"
        candidate.updated_at = datetime.utcnow()
        await db.commit()
        raise ValueError("NAS copy of this file still exists — item may be hot via mergerfs")

    rel_path = _relative_media_path(item.file_path)

    already_missing = False
    try:
        await _delete_cloud_file(rel_path)
    except Exception as exc:
        candidate.status = "failed"
        candidate.error_message = f"rclone delete failed: {exc}"
        candidate.updated_at = datetime.utcnow()
        await db.commit()
        logger.error("Deletion candidate %s: rclone delete failed for %s: %s", candidate.id, rel_path, exc)
        raise

    verified = await _verify_cloud_deleted(rel_path)
    if not verified:
        already_missing = True
        logger.info("Deletion candidate %s: cloud file was already missing: %s", candidate.id, rel_path)

    now = datetime.utcnow()
    candidate.status = "deleted"
    candidate.approved_at = now
    candidate.deleted_at = now
    candidate.updated_at = now
    if already_missing:
        candidate.error_message = "Cloud file was already missing"

    item.storage_tier = "deleted"
    item.transfer_direction = None
    item.deleted_at = now

    await db.commit()

    try:
        await _invalidate_vfs(rel_path)
    except Exception:
        pass

    logger.info("Deletion complete: %s", candidate.title)
    await broadcast({
        "type": "deletion_complete",
        "candidate_id": str(candidate.id),
        "title": candidate.title,
    })

    return candidate


async def protect_item_from_candidate(candidate_id: uuid.UUID, db: AsyncSession) -> DeletionException:
    result = await db.execute(
        select(DeletionCandidate).where(DeletionCandidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise ValueError("Candidate not found")

    exc = await protect_item(jellyfin_id=candidate.jellyfin_id, title=candidate.title, db=db)

    if candidate.status == "pending":
        candidate.status = "protected"
        candidate.updated_at = datetime.utcnow()
        await db.commit()

    return exc


async def protect_series_from_candidate(candidate_id: uuid.UUID, db: AsyncSession) -> DeletionException:
    result = await db.execute(
        select(DeletionCandidate).where(DeletionCandidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise ValueError("Candidate not found")

    if not candidate.series_id:
        raise ValueError("Candidate has no series_id")

    exc = await protect_series(series_id=candidate.series_id, title=candidate.series_name, db=db)

    pending_result = await db.execute(
        select(DeletionCandidate).where(
            DeletionCandidate.series_id == candidate.series_id,
            DeletionCandidate.status == "pending",
        )
    )
    now = datetime.utcnow()
    for c in pending_result.scalars():
        c.status = "protected"
        c.updated_at = now

    await db.commit()

    return exc


async def protect_item(jellyfin_id: str, db: AsyncSession, title: str | None = None, reason: str | None = None) -> DeletionException:
    existing_result = await db.execute(
        select(DeletionException).where(
            DeletionException.scope == "item",
            DeletionException.jellyfin_id == jellyfin_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return existing

    exc = DeletionException(
        scope="item",
        jellyfin_id=jellyfin_id,
        title=title,
        reason=reason,
    )
    db.add(exc)
    await db.flush()
    return exc


async def protect_items(jellyfin_ids: list[str], db: AsyncSession, reason: str | None = None) -> dict:
    created = 0
    skipped = 0
    for jid in jellyfin_ids:
        try:
            existing_result = await db.execute(
                select(DeletionException).where(
                    DeletionException.scope == "item",
                    DeletionException.jellyfin_id == jid,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            item_result = await db.execute(
                select(MediaItem).where(MediaItem.jellyfin_id == jid)
            )
            item = item_result.scalar_one_or_none()
            title = item.title if item else None

            db.add(DeletionException(
                scope="item",
                jellyfin_id=jid,
                title=title,
                reason=reason,
            ))
            created += 1
        except Exception:
            skipped += 1

    await db.flush()
    return {"created": created, "skipped": skipped}


async def protect_series(series_id: str, db: AsyncSession, title: str | None = None, reason: str | None = None) -> DeletionException:
    existing_result = await db.execute(
        select(DeletionException).where(
            DeletionException.scope == "series",
            DeletionException.series_id == series_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return existing

    exc = DeletionException(
        scope="series",
        series_id=series_id,
        title=title,
        reason=reason,
    )
    db.add(exc)
    await db.flush()
    return exc


async def remove_exception(exception_id: uuid.UUID, db: AsyncSession) -> None:
    result = await db.execute(
        select(DeletionException).where(DeletionException.id == exception_id)
    )
    exc = result.scalar_one_or_none()
    if not exc:
        raise ValueError("Exception not found")

    await db.delete(exc)
    await db.commit()

    await broadcast({"type": "deletion_exception_changed"})
