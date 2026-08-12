import json
import logging
import time

from fastapi import APIRouter, Request

from core.prefetcher import on_item_added, on_playback_progress, on_playback_start, on_playback_stop
from models.schemas import PlaybackEventIn

logger = logging.getLogger(__name__)
router = APIRouter()

# Per-session playback state. Key: f"{user_id}:{jellyfin_id}".
# Values: {"last_progress": float (monotonic), "start_ticks": int | None}
_sessions: dict[str, dict] = {}
_PROGRESS_INTERVAL_S = 30.0
_SESSION_STALE_S = 300.0  # treat a >5-min gap as a fresh session (crash/reopen)


def _play_duration(session: dict, event: PlaybackEventIn) -> int | None:
    """Seconds-of-new-playback since this session started, in Jellyfin ticks."""
    if session["start_ticks"] is None or event.position_ticks is None:
        return None
    return max(0, event.position_ticks - session["start_ticks"])


@router.post("/webhook/jellyfin", status_code=200)
async def receive_jellyfin_webhook(request: Request) -> dict:
    body = await request.body()
    if not body:
        logger.debug("Jellyfin webhook: empty body (template not configured?)")
        return {"ok": True}

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Jellyfin webhook: invalid JSON (%s): %r", exc, body[:500])
        return {"ok": True}

    event_type = payload.get("NotificationType")

    logger.info("Jellyfin webhook received: %s (ItemId=%s, Item.Id=%s)",
                event_type,
                payload.get("ItemId"),
                (payload.get("Item") or {}).get("Id"))

    if event_type in ("PlaybackStart", "PlaybackProgress", "PlaybackStop"):
        event = PlaybackEventIn.from_webhook(payload)
        session_key = f"{event.user_id}:{event.jellyfin_id}"
        session = _sessions.setdefault(session_key, {"last_progress": 0.0, "start_ticks": None})
        now = time.monotonic()

        # Stale session (client restarted without a clean stop) → fresh clock
        if now - session["last_progress"] > _SESSION_STALE_S:
            session["start_ticks"] = None
            session["last_progress"] = 0.0

        if event_type == "PlaybackStart" or session["last_progress"] == 0:
            was_first_progress = event_type == "PlaybackProgress"
            session["start_ticks"] = event.position_ticks
            session["last_progress"] = now
            if was_first_progress:
                logger.info("First progress for session %s — triggering prefetch", session_key)
                try:
                    await on_playback_start(event)
                except Exception as exc:
                    logger.error("Prefetch trigger failed for %s: %s", event.jellyfin_id, exc, exc_info=True)
            else:
                await on_playback_start(event)

        elif event_type == "PlaybackProgress" and now - session["last_progress"] >= _PROGRESS_INTERVAL_S:
            session["last_progress"] = now
            try:
                await on_playback_progress(event, play_duration_ticks=_play_duration(session, event))
            except Exception as exc:
                logger.error("Prefetch trigger failed for %s: %s", event.jellyfin_id, exc, exc_info=True)

        elif event_type == "PlaybackStop":
            try:
                await on_playback_stop(event, play_duration_ticks=_play_duration(session, event))
            except Exception as exc:
                logger.error("Playback stop handling failed for %s: %s", event.jellyfin_id, exc, exc_info=True)
            # Stop ends the session — the next play starts a fresh clock.
            _sessions.pop(session_key, None)

    elif event_type == "ItemAdded":
        await on_item_added(payload)

    else:
        logger.debug("Unhandled webhook type: %s", event_type)

    return {"ok": True}
