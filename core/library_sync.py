"""Library sync — syncs Jellyfin's item catalogue into media_items.

Strategy:
  1. Fetch all Jellyfin items page by page (compact extraction per page,
     full response discarded immediately to keep memory low).
  2. For each item, check if its NAS path exists to determine storage tier.
     NAS is local disk — fast. We never walk the cloud/mergerfs mount.
  3. Upsert into media_items.

Tdarr eligibility is NOT set here — the scheduler's sync_tdarr_eligibility()
job runs every 10 minutes and handles that separately.
"""

import asyncio
import logging
import os
from datetime import datetime

import httpx

from config import settings
from models.database import async_session_factory
from models.tables import MediaItem
from sqlalchemy import select

logger = logging.getLogger(__name__)

_JF_FIELDS = (
    "MediaSources,SeriesId,SeriesName,"
    "DateCreated,PremiereDate,CommunityRating,"
    "ParentIndexNumber,IndexNumber"
)
_JF_PAGE_SIZE = 500


def _resolution_label(height: int | None) -> str | None:
    if not height:
        return None
    if height >= 2160:
        return "4K"
    if height >= 1080:
        return "1080p"
    if height >= 720:
        return "720p"
    return f"{height}p"


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.rstrip("Z"))
    except ValueError:
        return None


def _extract_compact(item: dict, source: dict) -> dict:
    """Pull only the fields we need from a Jellyfin item + source pair."""
    streams = source.get("MediaStreams") or []
    video = next((s for s in streams if s.get("Type") == "Video"), None)
    return {
        "jellyfin_id": item["Id"].replace("-", ""),
        "title": item.get("Name", item["Id"]),
        "item_type": (item.get("Type") or "unknown").lower(),
        "series_id": item.get("SeriesId"),
        "series_name": item.get("SeriesName"),
        "season_number": item.get("ParentIndexNumber"),
        "episode_number": item.get("IndexNumber"),
        "date_added": _parse_dt(item.get("DateCreated")),
        "premiere_date": _parse_dt(item.get("PremiereDate")),
        "community_rating": item.get("CommunityRating"),
        "codec": ((video.get("Codec") or "").lower() or None) if video else None,
        "resolution": _resolution_label(video.get("Height") if video else None),
        "file_path": source.get("Path", ""),
        "file_size_bytes": source.get("Size") or 0,
    }


async def _fetch_path_map() -> dict[str, dict]:
    """
    Fetch all Jellyfin items page by page.
    Returns {absolute_file_path: compact_dict}.
    """
    path_map: dict[str, dict] = {}
    base = settings.jellyfin_url.rstrip("/")
    headers = {
        "Authorization": f'MediaBrowser Token="{settings.jellyfin_api_key}"',
        "Content-Type": "application/json",
    }
    start = 0
    total = None

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        while True:
            resp = await client.get(
                f"{base}/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": "Movie,Episode",
                    "Fields": _JF_FIELDS,
                    "StartIndex": start,
                    "Limit": _JF_PAGE_SIZE,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("TotalRecordCount", 0)
                logger.info("Library sync: %d Jellyfin items to fetch", total)

            page = data.get("Items") or []
            for item in page:
                for source in item.get("MediaSources") or []:
                    path = source.get("Path")
                    if path:
                        path_map[path] = _extract_compact(item, source)

            del data, page  # free memory immediately

            start += _JF_PAGE_SIZE
            if start >= (total or 0):
                break

    logger.info("Library sync: path map built (%d paths)", len(path_map))
    return path_map


async def run_library_sync() -> dict:
    """
    Sync Jellyfin catalogue → DB. No filesystem walk — NAS existence
    check per item is fast (local disk, no FUSE/cloud traversal).
    Returns {"total": N, "new": N, "updated": N, "removed": N}.
    """
    path_map = await _fetch_path_map()
    stats = {"total": 0, "new": 0, "updated": 0, "removed": 0}
    items = list(path_map.values())
    seen_jellyfin_ids = {c["jellyfin_id"] for c in items}
    logger.info("Library sync: upserting %d items...", len(items))

    async with async_session_factory() as db:
        for i, compact in enumerate(items):
            stats["total"] += 1

            # Yield to event loop every 100 items
            if i % 100 == 0:
                await asyncio.sleep(0)

            # Log progress every 500 items
            if i > 0 and i % 500 == 0:
                logger.info(
                    "Library sync progress: %d/%d (new=%d, updated=%d)",
                    i, len(items), stats["new"], stats["updated"],
                )

            file_path = compact["file_path"]
            if not file_path:
                continue

            # Tier: translate Jellyfin's internal path to the host NAS path.
            # Jellyfin mounts media at jellyfin_media_root (e.g. /media_2),
            # which maps to nas_root (e.g. /mnt/nas/media) on the host.
            try:
                rel = os.path.relpath(file_path, settings.jellyfin_media_root)
                nas_path = os.path.join(settings.nas_root, rel)
                tier = "hot" if os.path.exists(nas_path) else "cold"
            except ValueError:
                tier = "hot"

            # OpenDrive silently drops files with filenames > ~120 chars
            blocked = len(os.path.basename(file_path)) > 120

            result = await db.execute(
                select(MediaItem).where(MediaItem.jellyfin_id == compact["jellyfin_id"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.title = compact["title"]
                existing.series_id = compact["series_id"]
                existing.series_name = compact["series_name"]
                existing.season_number = compact["season_number"]
                existing.episode_number = compact["episode_number"]
                existing.file_path = file_path
                existing.file_size_bytes = compact["file_size_bytes"]
                existing.codec = compact["codec"]
                existing.resolution = compact["resolution"]
                existing.storage_tier = tier
                existing.upload_blocked = blocked
                existing.community_rating = compact["community_rating"]
                existing.premiere_date = compact["premiere_date"]
                existing.updated_at = datetime.utcnow()
                stats["updated"] += 1
            else:
                db.add(MediaItem(
                    jellyfin_id=compact["jellyfin_id"],
                    title=compact["title"],
                    item_type=compact["item_type"],
                    series_id=compact["series_id"],
                    series_name=compact["series_name"],
                    season_number=compact["season_number"],
                    episode_number=compact["episode_number"],
                    file_path=file_path,
                    file_size_bytes=compact["file_size_bytes"],
                    codec=compact["codec"],
                    resolution=compact["resolution"],
                    storage_tier=tier,
                    upload_blocked=blocked,
                    temperature=100.0,
                    date_added=compact["date_added"],
                    premiere_date=compact["premiere_date"],
                    community_rating=compact["community_rating"],
                ))
                stats["new"] += 1

            # Commit in batches of 500
            if stats["total"] % 500 == 0:
                await db.commit()

        await db.commit()

        # --- Orphan cleanup: remove items Jellyfin no longer reports ---
        if seen_jellyfin_ids:
            all_db_ids_result = await db.execute(
                select(MediaItem.jellyfin_id)
            )
            all_db_ids = {row[0] for row in all_db_ids_result.all()}
            orphan_ids = all_db_ids - seen_jellyfin_ids

            if orphan_ids:
                logger.info(
                    "Library sync: removing %d orphaned items no longer in Jellyfin",
                    len(orphan_ids),
                )
                orphan_result = await db.execute(
                    select(MediaItem).where(MediaItem.jellyfin_id.in_(orphan_ids))
                )
                for orphan in orphan_result.scalars():
                    logger.debug("Removing orphan: %s — %s", orphan.title, orphan.file_path)
                    await db.delete(orphan)
                    stats["removed"] += 1
                await db.commit()

    logger.info(
        "Library sync complete: %d total, %d new, %d updated, %d removed",
        stats["total"], stats["new"], stats["updated"], stats["removed"],
    )
    return stats
