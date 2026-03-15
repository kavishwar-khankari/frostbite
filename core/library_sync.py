"""Library sync — walks the filesystem and populates media_items from Jellyfin.

Strategy:
  1. Fetch Jellyfin items page by page (500/page). For each page, extract
     only the fields we need into a compact dict, then discard the full
     response so we never hold all 10k items in memory at once.
  2. Walk iter_media_files() and match each file to the compact dict by path.
  3. Upsert into media_items (insert new, update existing).

Tdarr eligibility is intentionally NOT checked here — it runs every 10 min
via sync_tdarr_eligibility() in the scheduler, keeping this sync lightweight.

File paths in the DB are stored as absolute paths as reported by Jellyfin
(e.g. /mnt/merged/media/TV/Show/S01/ep.mkv).
"""

import asyncio
import logging
import os
from datetime import datetime

import httpx

from config import settings
from core.filesystem import iter_media_files
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
    """Extract only the fields we need from a Jellyfin item + source pair."""
    streams = source.get("MediaStreams") or []
    video = next((s for s in streams if s.get("Type") == "Video"), None)
    return {
        "jellyfin_id": item["Id"],
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
    }


async def _fetch_path_map() -> dict[str, dict]:
    """
    Fetch all Jellyfin items page by page and build a compact
    {absolute_path: compact_dict} map without holding all raw responses.
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

            # Explicitly release the large response
            del data, page

            start += _JF_PAGE_SIZE
            if start >= (total or 0):
                break

    logger.info("Library sync: path map built (%d paths)", len(path_map))
    return path_map


async def run_library_sync() -> dict:
    """
    Sync the filesystem → Jellyfin → DB.
    Returns {"total": N, "new": N, "updated": N, "unmatched": N}.
    """
    path_map = await _fetch_path_map()
    stats = {"total": 0, "new": 0, "updated": 0, "unmatched": 0}

    # os.walk() on a FUSE/mergerfs mount is blocking and slow.
    # Run it entirely in a thread so the event loop stays free for health checks.
    logger.info("Library sync: scanning filesystem (this may take a minute)...")
    all_files: list[tuple[str, str, int]] = await asyncio.to_thread(
        lambda: list(iter_media_files())
    )
    logger.info("Library sync: found %d files on disk", len(all_files))

    async with async_session_factory() as db:
        for full_path, _rel_path, size_bytes in all_files:
            stats["total"] += 1

            # Yield to event loop every 100 files and log progress every 500
            if stats["total"] % 100 == 0:
                await asyncio.sleep(0)
            if stats["total"] % 500 == 0:
                logger.info(
                    "Library sync progress: %d/%d files (new=%d, updated=%d, unmatched=%d)",
                    stats["total"], len(all_files),
                    stats["new"], stats["updated"], stats["unmatched"],
                )

            compact = path_map.get(full_path)
            if compact is None:
                stats["unmatched"] += 1
                logger.debug("Library sync: no Jellyfin match for %s", _rel_path)
                continue

            # Fast tier check: if the file exists on NAS, it's hot. No subprocess.
            rel = os.path.relpath(full_path, settings.media_root)
            tier = "hot" if os.path.exists(os.path.join(settings.nas_root, rel)) else "cold"

            result = await db.execute(
                select(MediaItem).where(MediaItem.jellyfin_id == compact["jellyfin_id"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.file_path = full_path
                existing.file_size_bytes = size_bytes
                existing.codec = compact["codec"]
                existing.resolution = compact["resolution"]
                existing.storage_tier = tier
                existing.community_rating = compact["community_rating"]
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
                    file_path=full_path,
                    file_size_bytes=size_bytes,
                    codec=compact["codec"],
                    resolution=compact["resolution"],
                    storage_tier=tier,
                    temperature=100.0,
                    date_added=compact["date_added"],
                    premiere_date=compact["premiere_date"],
                    community_rating=compact["community_rating"],
                ))
                stats["new"] += 1

            # Commit in batches of 500 to avoid holding a huge transaction
            if stats["total"] % 500 == 0:
                await db.commit()

        await db.commit()

    logger.info(
        "Library sync complete: %d total, %d new, %d updated, %d unmatched",
        stats["total"], stats["new"], stats["updated"], stats["unmatched"],
    )
    return stats
