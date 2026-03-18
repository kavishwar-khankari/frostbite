"""DB-backed runtime settings overlay.

Stores overrides for UI-editable config keys in the app_settings table.
Call load_overrides() at startup. All existing code that reads from
`config.settings` will automatically see updated values because we
patch the settings object in-place.
"""

import logging
from datetime import datetime

from sqlalchemy import select

from config import settings
from models.database import async_session_factory

logger = logging.getLogger(__name__)

# Keys the UI is allowed to edit and their expected Python types
EDITABLE_KEYS: dict[str, type] = {
    "freeze_threshold": float,
    "reheat_threshold": float,
    "prefetch_boost": float,
    "prefetch_cooldown_days": int,
    "freeze_window_start": int,
    "freeze_window_end": int,
    "max_concurrent_reheats": int,
    "max_concurrent_freezes": int,
    "emergency_freeze_threshold_gb": float,
}


async def load_overrides() -> None:
    """Apply any DB-persisted overrides to the settings object at startup."""
    from models.tables import AppSettings
    try:
        async with async_session_factory() as db:
            result = await db.execute(select(AppSettings))
            for row in result.scalars():
                if row.key in EDITABLE_KEYS:
                    cast = EDITABLE_KEYS[row.key]
                    setattr(settings, row.key, cast(row.value))
                    logger.info("Setting override loaded: %s = %s", row.key, row.value)
    except Exception as exc:
        logger.warning("Could not load settings overrides from DB: %s", exc)


async def save_override(key: str, value) -> None:
    """Persist a setting override to DB and apply it in-memory immediately."""
    from models.tables import AppSettings
    if key not in EDITABLE_KEYS:
        raise ValueError(f"Not an editable setting: {key}")
    cast = EDITABLE_KEYS[key]
    typed_value = cast(value)
    setattr(settings, key, typed_value)

    async with async_session_factory() as db:
        result = await db.execute(select(AppSettings).where(AppSettings.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = str(typed_value)
            existing.updated_at = datetime.utcnow()
        else:
            db.add(AppSettings(key=key, value=str(typed_value)))
        await db.commit()


def get_all() -> dict:
    """Return current values of all editable settings."""
    return {k: getattr(settings, k) for k in EDITABLE_KEYS}
