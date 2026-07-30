import asyncio
from types import SimpleNamespace

import pytest

from core import runtime_settings


class ScalarResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


    def scalars(self):
        return self.value


class FakeSession:
    def __init__(self, result):
        self.result = result
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return self.result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def test_save_override_updates_existing_row_and_in_memory_setting(monkeypatch):
    existing = SimpleNamespace(value="25.0", updated_at=None)
    session = FakeSession(ScalarResult(existing))
    monkeypatch.setattr(runtime_settings, "async_session_factory", lambda: session)
    monkeypatch.setattr(runtime_settings.settings, "freeze_threshold", runtime_settings.settings.freeze_threshold)

    asyncio.run(runtime_settings.save_override("freeze_threshold", "12.5"))

    assert runtime_settings.settings.freeze_threshold == 12.5
    assert existing.value == "12.5"
    assert existing.updated_at is not None
    assert session.added == []
    assert session.committed is True


def test_save_override_inserts_new_row(monkeypatch):
    session = FakeSession(ScalarResult(None))
    monkeypatch.setattr(runtime_settings, "async_session_factory", lambda: session)
    monkeypatch.setattr(
        runtime_settings.settings,
        "prefetch_cooldown_days",
        runtime_settings.settings.prefetch_cooldown_days,
    )

    asyncio.run(runtime_settings.save_override("prefetch_cooldown_days", "7"))

    assert runtime_settings.settings.prefetch_cooldown_days == 7
    assert len(session.added) == 1
    assert session.added[0].key == "prefetch_cooldown_days"
    assert session.added[0].value == "7"
    assert session.committed is True


def test_manual_reheat_freeze_window_days_is_editable(monkeypatch):
    session = FakeSession(ScalarResult(None))
    monkeypatch.setattr(runtime_settings, "async_session_factory", lambda: session)
    monkeypatch.setattr(
        runtime_settings.settings,
        "manual_reheat_freeze_window_days",
        runtime_settings.settings.manual_reheat_freeze_window_days,
    )

    asyncio.run(runtime_settings.save_override("manual_reheat_freeze_window_days", "5"))

    assert runtime_settings.settings.manual_reheat_freeze_window_days == 5
    assert session.added[0].key == "manual_reheat_freeze_window_days"
    assert session.added[0].value == "5"
    assert "manual_reheat_freeze_window_days" in runtime_settings.EDITABLE_KEYS


def test_save_override_rejects_non_editable_setting(monkeypatch):
    monkeypatch.setattr(
        runtime_settings,
        "async_session_factory",
        lambda: pytest.fail("database should not be opened"),
    )

    with pytest.raises(ValueError, match="Not an editable setting"):
        asyncio.run(runtime_settings.save_override("database_url", "sqlite://"))


def test_load_overrides_casts_editable_rows_and_ignores_others(monkeypatch):
    rows = [
        SimpleNamespace(key="freeze_threshold", value="11.5"),
        SimpleNamespace(key="max_concurrent_reheats", value="4"),
        SimpleNamespace(key="database_url", value="postgresql://ignored"),
    ]
    session = FakeSession(ScalarResult(rows))
    monkeypatch.setattr(runtime_settings, "async_session_factory", lambda: session)
    monkeypatch.setattr(runtime_settings.settings, "freeze_threshold", runtime_settings.settings.freeze_threshold)
    monkeypatch.setattr(
        runtime_settings.settings,
        "max_concurrent_reheats",
        runtime_settings.settings.max_concurrent_reheats,
    )
    original_database_url = runtime_settings.settings.database_url

    asyncio.run(runtime_settings.load_overrides())

    assert runtime_settings.settings.freeze_threshold == 11.5
    assert runtime_settings.settings.max_concurrent_reheats == 4
    assert runtime_settings.settings.database_url == original_database_url
