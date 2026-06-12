from datetime import datetime, timedelta

from core.freeze_policy import (
    freeze_start_blocker,
    prefetch_protected_until,
    queued_transfer_cancel_reason,
    reheat_start_blocker,
)


def test_prefetch_protection_expires_or_clears_when_watched():
    now = datetime(2026, 6, 12, 12, 0, 0)
    last_prefetch = now - timedelta(hours=4)

    assert prefetch_protected_until(
        last_prefetch,
        False,
        now,
        12,
        item_storage_tier="hot",
    ) == last_prefetch + timedelta(hours=12)
    assert prefetch_protected_until(last_prefetch, True, now, 12, item_storage_tier="hot") is None
    assert prefetch_protected_until(now - timedelta(hours=13), False, now, 12, item_storage_tier="hot") is None
    assert prefetch_protected_until(None, False, now, 12, item_storage_tier="hot") is None


def test_prefetch_protection_only_applies_to_hot_items():
    now = datetime(2026, 6, 12, 12, 0, 0)
    last_prefetch = now - timedelta(hours=4)

    assert prefetch_protected_until(last_prefetch, False, now, 12, item_storage_tier="cold") is None


def test_auto_freeze_cancelled_for_prefetch_but_manual_freeze_is_kept():
    reason = queued_transfer_cancel_reason(
        direction="freeze",
        trigger="auto_score",
        item_storage_tier="hot",
        item_temperature=5.0,
        freeze_threshold=25.0,
        reheat_threshold=60.0,
        upload_blocked=False,
        prefetch_protected=True,
    )
    assert reason == "Recently prefetched and waiting to be watched"

    manual_reason = queued_transfer_cancel_reason(
        direction="freeze",
        trigger="manual",
        item_storage_tier="hot",
        item_temperature=5.0,
        freeze_threshold=25.0,
        reheat_threshold=60.0,
        upload_blocked=False,
        prefetch_protected=True,
    )
    assert manual_reason is None


def test_score_based_cancellation_only_applies_to_auto_score():
    auto_reason = queued_transfer_cancel_reason(
        direction="freeze",
        trigger="auto_score",
        item_storage_tier="hot",
        item_temperature=25.0,
        freeze_threshold=25.0,
        reheat_threshold=60.0,
        upload_blocked=False,
        prefetch_protected=False,
    )
    assert auto_reason == "Temperature rose above freeze threshold"

    manual_reason = queued_transfer_cancel_reason(
        direction="reheat",
        trigger="manual",
        item_storage_tier="cold",
        item_temperature=10.0,
        freeze_threshold=25.0,
        reheat_threshold=60.0,
        upload_blocked=False,
        prefetch_protected=False,
    )
    assert manual_reason is None


def test_impossible_transfer_states_are_cancelled_for_all_triggers():
    assert queued_transfer_cancel_reason(
        direction="freeze",
        trigger="manual",
        item_storage_tier="cold",
        item_temperature=5.0,
        freeze_threshold=25.0,
        reheat_threshold=60.0,
        upload_blocked=False,
        prefetch_protected=False,
    ) == "Item is no longer hot"
    assert queued_transfer_cancel_reason(
        direction="freeze",
        trigger="space_pressure",
        item_storage_tier="hot",
        item_temperature=5.0,
        freeze_threshold=25.0,
        reheat_threshold=60.0,
        upload_blocked=True,
        prefetch_protected=False,
    ) == "Filename too long for cloud storage"


def test_freeze_start_blocker_priority_order():
    assert freeze_start_blocker(
        paused=False,
        active_freezes=0,
        queued_freezes=0,
        max_concurrent_freezes=2,
        freeze_window_active=True,
        gate_can_start=True,
        gate_reason=None,
    )[0] == "no_queued_freezes"
    assert freeze_start_blocker(
        paused=True,
        active_freezes=0,
        queued_freezes=1,
        max_concurrent_freezes=2,
        freeze_window_active=True,
        gate_can_start=True,
        gate_reason=None,
    )[0] == "global_pause"
    assert freeze_start_blocker(
        paused=False,
        active_freezes=2,
        queued_freezes=1,
        max_concurrent_freezes=2,
        freeze_window_active=True,
        gate_can_start=True,
        gate_reason=None,
    )[0] == "freeze_concurrency"
    assert freeze_start_blocker(
        paused=False,
        active_freezes=0,
        queued_freezes=1,
        max_concurrent_freezes=2,
        freeze_window_active=False,
        gate_can_start=True,
        gate_reason=None,
    )[0] == "freeze_window"
    assert freeze_start_blocker(
        paused=False,
        active_freezes=0,
        queued_freezes=1,
        max_concurrent_freezes=2,
        freeze_window_active=True,
        gate_can_start=False,
        gate_reason="below limit",
    ) == ("nas_usage_gate", "below limit")
    assert freeze_start_blocker(
        paused=False,
        active_freezes=0,
        queued_freezes=1,
        max_concurrent_freezes=2,
        freeze_window_active=True,
        gate_can_start=True,
        gate_reason=None,
    ) == ("none", None)


def test_reheat_start_blocker():
    assert reheat_start_blocker(
        paused=False,
        active_reheats=0,
        queued_reheats=0,
        max_concurrent_reheats=2,
    )[0] == "no_queued_reheats"
    assert reheat_start_blocker(
        paused=True,
        active_reheats=0,
        queued_reheats=1,
        max_concurrent_reheats=2,
    )[0] == "global_pause"
    assert reheat_start_blocker(
        paused=False,
        active_reheats=2,
        queued_reheats=1,
        max_concurrent_reheats=2,
    )[0] == "reheat_concurrency"
    assert reheat_start_blocker(
        paused=False,
        active_reheats=0,
        queued_reheats=1,
        max_concurrent_reheats=2,
    ) == ("none", None)
