import logging

from fastapi import APIRouter, Request

from core.prefetcher import on_item_added, on_playback_progress, on_playback_start, on_playback_stop
from models.schemas import PlaybackEventIn

logger = logging.getLogger(__name__)
router = APIRouter()

# Track last progress event time per session to avoid processing every tick.
_last_progress: dict[str, float] = {}
_PROGRESS_INTERVAL_S = 30.0


@router.post("/webhook/jellyfin", status_code=200)
async def receive_jellyfin_webhook(request: Request) -> dict:
    body = await request.body()
    if not body:
        logger.debug("Jellyfin webhook: empty body (template not configured?)")
        return {"ok": True}

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Jellyfin webhook: invalid JSON body: %r", body[:200])
        return {"ok": True}

    event_type = payload.get("NotificationType")

    logger.info("Jellyfin webhook received: %s", event_type)

    if event_type == "PlaybackStart":
        event = PlaybackEventIn.from_webhook(payload)
        await on_playback_start(event)

    elif event_type == "PlaybackStop":
        event = PlaybackEventIn.from_webhook(payload)
        await on_playback_stop(event)

    elif event_type == "PlaybackProgress":
        import time

        event = PlaybackEventIn.from_webhook(payload)
        session_key = f"{event.user_id}:{event.jellyfin_id}"
        now = time.monotonic()

        if now - _last_progress.get(session_key, 0) >= _PROGRESS_INTERVAL_S:
            _last_progress[session_key] = now
            await on_playback_progress(event)

    elif event_type == "ItemAdded":
        await on_item_added(payload)

    else:
        logger.debug("Unhandled webhook type: %s", event_type)

    return {"ok": True}
