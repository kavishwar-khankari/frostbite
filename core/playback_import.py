"""
Incremental playback sync from the Jellyfin Playback Reporting plugin.

The Playback Reporting plugin (already installed, stores all historical data)
is Frostbite's source of truth for playback events.  This module polls the
plugin's REST API every few minutes, fetching only rows newer than the last
successful sync, and writing them into our playback_events table.

This approach is better than webhooks for scoring because:
  - It has full historical data (years of plays, not just from Frostbite's
    deployment date)
  - It self-heals: if Frostbite is down, the next poll catches up
  - No extra Jellyfin plugin config needed — Playback Reporting is already
    installed and collecting data

The last-synced timestamp is stored in app_settings under the key
'playback_sync_cursor' so incremental syncs survive pod restarts.
"""

import logging
from datetime import datetime

import httpx
from sqlalchemy import delete, select, text

from config import settings
from models.database import async_session_factory
from models.tables import AppSettings, MediaItem, PlaybackEvent

logger = logging.getLogger(__name__)

_CURSOR_KEY = "playback_sync_cursor"
# Tag used only on the initial full-history backfill so it can be re-run cleanly.
# Incremental rows use the real client_name from Jellyfin.
_BACKFILL_TAG = "__backfill__"


def _make_query(since: datetime | None) -> str:
    """Build the SQL string to send to the plugin's submit_custom_query endpoint."""
    base = """
SELECT
    DateCreated,
    UserId,
    ItemId,
    PlayDuration,
    ClientName,
    DeviceName
FROM PlaybackActivity
WHERE ItemType IN ('Episode', 'Movie')
"""
    if since:
        # Use ISO format without timezone — the plugin DB stores naive UTC strings.
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
        base += f"  AND DateCreated > '{since_str}'\n"
    base += "ORDER BY DateCreated"
    return base


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        ts = raw.strip()
        if "." in ts:
            base, frac = ts.rsplit(".", 1)
            ts = f"{base}.{frac[:6]}"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


async def _get_cursor(db) -> datetime | None:
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == _CURSOR_KEY)
    )
    row = result.scalar_one_or_none()
    if row:
        return _parse_date(row.value)
    return None


async def _set_cursor(db, ts: datetime) -> None:
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == _CURSOR_KEY)
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = ts.isoformat()
    else:
        db.add(AppSettings(key=_CURSOR_KEY, value=ts.isoformat()))


async def sync_playback_from_reporting(full_reimport: bool = False) -> dict:
    """
    Incremental sync from the Jellyfin Playback Reporting plugin.

    full_reimport=True: wipe existing backfill rows, reset cursor, import
      everything from the beginning of time.  Use this once to seed historical
      data.

    full_reimport=False (default, runs every 5 min): fetch only rows newer
      than the last cursor, append to playback_events.
    """
    headers = {
        "Authorization": f"MediaBrowser Token={settings.jellyfin_api_key}",
        "Content-Type": "application/json",
    }

    async with async_session_factory() as db:
        if full_reimport:
            # Wipe previous backfill so the import is idempotent
            await db.execute(
                delete(PlaybackEvent).where(PlaybackEvent.client_name == _BACKFILL_TAG)
            )
            # Also wipe incremental rows — start completely fresh
            await db.execute(delete(PlaybackEvent))
            # Reset cursor
            await db.execute(
                delete(AppSettings).where(AppSettings.key == _CURSOR_KEY)
            )
            await db.commit()
            since = None
            tag = _BACKFILL_TAG
            logger.info("Playback sync: full reimport requested, cursor reset")
        else:
            since = await _get_cursor(db)
            tag = None  # keep real client name for incremental rows
            if since:
                logger.debug("Playback sync: fetching rows since %s", since.isoformat())
            else:
                logger.info("Playback sync: no cursor yet — first-time full import")
                tag = _BACKFILL_TAG

    query_sql = _make_query(since)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.jellyfin_url}/user_usage_stats/submit_custom_query",
            json={"CustomQueryString": query_sql, "ReplaceUserId": False},
            headers=headers,
        )

    if resp.status_code != 200:
        msg = f"Plugin API returned {resp.status_code}: {resp.text[:300]}"
        logger.error("Playback sync failed: %s", msg)
        return {"status": "error", "detail": msg}

    data = resp.json()
    # The plugin has a typo in its response key: "colums" instead of "columns"
    columns = data.get("colums") or data.get("columns") or []
    rows = data.get("results") or []

    if not rows:
        logger.debug("Playback sync: no new rows since last sync")
        return {"status": "ok", "imported": 0, "skipped": 0}

    logger.info("Playback sync: %d new rows from plugin", len(rows))

    col = {name: i for i, name in enumerate(columns)}

    async with async_session_factory() as db:
        # Build jellyfin_id → internal UUID lookup
        result = await db.execute(select(MediaItem.id, MediaItem.jellyfin_id))
        id_map: dict[str, object] = {row.jellyfin_id: row.id for row in result}

        imported = skipped = 0
        newest_ts: datetime | None = None
        batch: list[PlaybackEvent] = []

        for row in rows:
            jellyfin_id = row[col.get("ItemId", -1)] if "ItemId" in col else None
            user_id     = row[col.get("UserId", -1)] if "UserId" in col else None
            date_raw    = row[col.get("DateCreated", -1)] if "DateCreated" in col else None
            play_dur    = row[col.get("PlayDuration", -1)] if "PlayDuration" in col else 0
            client_name = row[col.get("ClientName", -1)] if "ClientName" in col else None
            device_name = row[col.get("DeviceName", -1)] if "DeviceName" in col else None

            if not jellyfin_id or not user_id:
                skipped += 1
                continue

            media_item_id = id_map.get(jellyfin_id)
            if not media_item_id:
                skipped += 1
                continue

            created_at = _parse_date(date_raw)
            if not created_at:
                skipped += 1
                continue

            batch.append(PlaybackEvent(
                media_item_id=media_item_id,
                user_id=user_id,
                event_type="start",
                play_method=None,
                position_ticks=None,
                duration_ticks=int(play_dur) * 10_000_000 if play_dur else None,
                client_name=tag or client_name,
                device_name=device_name,
                username=None,
                created_at=created_at,
            ))
            imported += 1

            if newest_ts is None or created_at > newest_ts:
                newest_ts = created_at

            if len(batch) >= 2000:
                db.add_all(batch)
                await db.flush()
                batch = []

        if batch:
            db.add_all(batch)

        # Advance the cursor to the newest row we just imported
        if newest_ts:
            await _set_cursor(db, newest_ts)

        await db.commit()

    # Refresh the materialized view so scorer sees the new data
    async with async_session_factory() as db:
        try:
            await db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY item_playback_stats"))
            await db.commit()
        except Exception as exc:
            logger.warning("Could not refresh materialized view: %s", exc)

    logger.info(
        "Playback sync complete: %d events imported, %d skipped, cursor=%s",
        imported, skipped, newest_ts,
    )
    return {"status": "ok", "imported": imported, "skipped": skipped}
