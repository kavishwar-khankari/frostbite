"""Library sync — walks the filesystem and populates media_items from Jellyfin.

Strategy:
  1. Fetch all Jellyfin items (Movies + Episodes) in one paginated call.
  2. Build a dict: absolute_file_path → (jellyfin_item, media_source).
  3. Fetch Tdarr eligible files once.
  4. Walk iter_media_files() and match each file to Jellyfin by path.
  5. Upsert into media_items (insert new, update existing).

File paths in the DB are stored as absolute paths as reported by Jellyfin
(e.g. /mnt/merged/media/TV/Show/S01/ep.mkv).
"""

import logging
import os
from datetime import datetime

from sqlalchemy import select

from config import settings
from core.filesystem import get_storage_tier, iter_media_files
from core.jellyfin_client import JellyfinClient
from core.tdarr_client import TdarrClient
from models.database import async_session_factory
from models.tables import MediaItem

logger = logging.getLogger(__name__)


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


def _tdarr_match(file_path: str, eligible_paths: set[str]) -> bool:
    """Check eligibility with flexible mount-agnostic suffix matching."""
    if file_path in eligible_paths:
        return True
    # Tdarr may use a different mount point — match on the relative portion
    try:
        rel = os.path.relpath(file_path, settings.media_root)
        return any(p.endswith(rel) for p in eligible_paths)
    except ValueError:
        return False


async def run_library_sync() -> dict:
    """
    Sync the filesystem → Jellyfin → DB.
    Returns {"total": N, "new": N, "updated": N, "unmatched": N}.
    """
    jf = JellyfinClient()
    tdarr = TdarrClient()

    # ── 1. Fetch Jellyfin items ───────────────────────────────────────────────
    logger.info("Library sync: fetching Jellyfin items...")
    jf_items = await jf.get_all_items()
    logger.info("Library sync: got %d Jellyfin items", len(jf_items))

    # Build lookup: absolute path → (item dict, source dict)
    path_map: dict[str, tuple[dict, dict]] = {}
    for item in jf_items:
        for source in item.get("MediaSources") or []:
            path = source.get("Path")
            if path:
                path_map[path] = (item, source)

    # ── 2. Fetch Tdarr eligibility ────────────────────────────────────────────
    logger.info("Library sync: fetching Tdarr eligibility...")
    tdarr_files = await tdarr.get_eligible_files()
    eligible_paths: set[str] = {
        f.get("_id") or f.get("file")
        for f in tdarr_files
        if f.get("_id") or f.get("file")
    }
    logger.info("Library sync: %d Tdarr-eligible paths", len(eligible_paths))

    # ── 3. Walk filesystem and upsert ─────────────────────────────────────────
    stats = {"total": 0, "new": 0, "updated": 0, "unmatched": 0}

    async with async_session_factory() as db:
        for full_path, rel_path, size_bytes in iter_media_files():
            stats["total"] += 1

            match = path_map.get(full_path)
            if match is None:
                stats["unmatched"] += 1
                logger.debug("Library sync: no Jellyfin match for %s", rel_path)
                continue

            jf_item, source = match

            # Codec + resolution from the video MediaStream
            streams = source.get("MediaStreams") or []
            video = next((s for s in streams if s.get("Type") == "Video"), None)
            codec = ((video.get("Codec") or "").lower() or None) if video else None
            resolution = _resolution_label(video.get("Height") if video else None)

            tier = get_storage_tier(full_path)
            tdarr_ok = _tdarr_match(full_path, eligible_paths)
            jellyfin_id = jf_item["Id"]

            result = await db.execute(
                select(MediaItem).where(MediaItem.jellyfin_id == jellyfin_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.file_path = full_path
                existing.file_size_bytes = size_bytes
                existing.codec = codec
                existing.resolution = resolution
                existing.storage_tier = tier
                # Don't downgrade eligibility if already set
                if tdarr_ok:
                    existing.tdarr_eligible = True
                    existing.tdarr_status = "done"
                existing.community_rating = jf_item.get("CommunityRating")
                existing.updated_at = datetime.utcnow()
                stats["updated"] += 1
            else:
                db.add(MediaItem(
                    jellyfin_id=jellyfin_id,
                    title=jf_item.get("Name", jellyfin_id),
                    item_type=(jf_item.get("Type") or "unknown").lower(),
                    series_id=jf_item.get("SeriesId"),
                    series_name=jf_item.get("SeriesName"),
                    season_number=jf_item.get("ParentIndexNumber"),
                    episode_number=jf_item.get("IndexNumber"),
                    file_path=full_path,
                    file_size_bytes=size_bytes,
                    codec=codec,
                    resolution=resolution,
                    tdarr_eligible=tdarr_ok,
                    tdarr_status="done" if tdarr_ok else None,
                    storage_tier=tier,
                    temperature=100.0,
                    date_added=_parse_dt(jf_item.get("DateCreated")),
                    premiere_date=_parse_dt(jf_item.get("PremiereDate")),
                    community_rating=jf_item.get("CommunityRating"),
                ))
                stats["new"] += 1

        await db.commit()

    logger.info(
        "Library sync complete: %d total, %d new, %d updated, %d unmatched",
        stats["total"], stats["new"], stats["updated"], stats["unmatched"],
    )
    return stats
