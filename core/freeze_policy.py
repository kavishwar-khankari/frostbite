"""Pure decision helpers for freeze queue and prefetch protection."""

from datetime import datetime, timedelta


def prefetch_protected_until(
    last_prefetch_at: datetime | None,
    watched_after_prefetch: bool,
    now: datetime,
    grace_hours: int,
    *,
    item_storage_tier: str,
) -> datetime | None:
    """Return the protection expiry if an item should not auto-freeze yet."""
    if not last_prefetch_at or watched_after_prefetch:
        return None
    if item_storage_tier != "hot":
        return None

    protected_until = last_prefetch_at + timedelta(hours=grace_hours)
    return protected_until if protected_until > now else None


def is_prefetch_protected(
    last_prefetch_at: datetime | None,
    watched_after_prefetch: bool,
    now: datetime,
    grace_hours: int,
    *,
    item_storage_tier: str,
) -> bool:
    return prefetch_protected_until(
        last_prefetch_at,
        watched_after_prefetch,
        now,
        grace_hours,
        item_storage_tier=item_storage_tier,
    ) is not None


def manual_reheat_protected_until(
    last_manual_reheat_at: datetime | None,
    now: datetime,
    grace_days: int,
    *,
    item_storage_tier: str,
) -> datetime | None:
    """Return expiry if a manual reheat should block automatic freezes."""
    if not last_manual_reheat_at or grace_days <= 0:
        return None
    if item_storage_tier != "hot":
        return None

    protected_until = last_manual_reheat_at + timedelta(days=grace_days)
    return protected_until if protected_until > now else None


def is_manual_reheat_protected(
    last_manual_reheat_at: datetime | None,
    now: datetime,
    grace_days: int,
    *,
    item_storage_tier: str,
) -> bool:
    return manual_reheat_protected_until(
        last_manual_reheat_at,
        now,
        grace_days,
        item_storage_tier=item_storage_tier,
    ) is not None


def manual_reheat_protection_map(
    items,
    now: datetime | None = None,
    grace_days: int | None = None,
) -> dict:
    """Return protected-until timestamps keyed by media item id."""
    from config import settings

    now = now or datetime.utcnow()
    if grace_days is None:
        grace_days = settings.manual_reheat_freeze_window_days
    return {
        item.id: manual_reheat_protected_until(
            getattr(item, "last_manual_reheat_at", None),
            now,
            grace_days,
            item_storage_tier=item.storage_tier,
        )
        for item in items
        if item
    }


def queued_transfer_cancel_reason(
    *,
    direction: str,
    trigger: str,
    item_storage_tier: str,
    item_temperature: float,
    freeze_threshold: float,
    reheat_threshold: float,
    upload_blocked: bool,
    prefetch_protected: bool,
    manual_reheat_protected: bool = False,
) -> str | None:
    """Return why a queued transfer is stale/unsafe, or None if it should remain."""
    if direction == "freeze":
        if item_storage_tier != "hot":
            return "Item is no longer hot"
        if upload_blocked:
            return "Filename too long for cloud storage"
        if trigger in ("auto_score", "space_pressure") and manual_reheat_protected:
            return "Protected after manual reheat"
        if trigger == "auto_score":
            if item_temperature >= freeze_threshold:
                return "Temperature rose above freeze threshold"
            if prefetch_protected:
                return "Recently prefetched and waiting to be watched"
        return None

    if direction == "reheat":
        if item_storage_tier != "cold":
            return "Item is no longer cold"
        if trigger == "auto_score" and item_temperature <= reheat_threshold:
            return "Temperature fell below reheat threshold"
        return None

    return f"Unknown transfer direction: {direction}"


def freeze_start_blocker(
    *,
    paused: bool,
    active_freezes: int,
    queued_freezes: int,
    max_concurrent_freezes: int,
    freeze_window_active: bool,
    gate_can_start: bool,
    gate_reason: str | None,
) -> tuple[str, str | None]:
    """Return the immediate reason the next queued freeze cannot start."""
    if queued_freezes <= 0:
        return "no_queued_freezes", None
    if paused:
        return "global_pause", "Transfer worker is paused."
    if active_freezes >= max_concurrent_freezes:
        return "freeze_concurrency", "Maximum active freeze transfers are already running."
    if not freeze_window_active:
        return "freeze_window", "Freeze transfers are outside the configured start window."
    if not gate_can_start:
        return "nas_usage_gate", gate_reason
    return "none", None


def reheat_start_blocker(
    *,
    paused: bool,
    active_reheats: int,
    queued_reheats: int,
    max_concurrent_reheats: int,
) -> tuple[str, str | None]:
    """Return the immediate reason the next queued reheat cannot start."""
    if queued_reheats <= 0:
        return "no_queued_reheats", None
    if paused:
        return "global_pause", "Transfer worker is paused."
    if active_reheats >= max_concurrent_reheats:
        return "reheat_concurrency", "Maximum active reheat transfers are already running."
    return "none", None
