import asyncio
import uuid
from datetime import datetime, timedelta

from core import prefetch_state
from models.tables import MediaItem


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, rows=(), error=None):
        self.rows = rows
        self.error = error
        self.executed = False

    async def execute(self, statement):
        self.executed = True
        if self.error:
            raise self.error
        return FakeResult(self.rows)


def item(*, storage_tier="hot", last_prefetch_at=None):
    return MediaItem(
        id=uuid.uuid4(),
        jellyfin_id=uuid.uuid4().hex,
        title="Test Item",
        item_type="movie",
        file_path="/media_2/Test.mkv",
        file_size_bytes=1024,
        storage_tier=storage_tier,
        last_prefetch_at=last_prefetch_at,
    )


def test_prefetch_protection_map_clears_items_watched_after_prefetch(monkeypatch):
    now = datetime(2026, 6, 12, 12, 0, 0)
    monkeypatch.setattr(prefetch_state.settings, "prefetch_grace_hours", 12)
    protected = item(last_prefetch_at=now - timedelta(hours=4))
    watched = item(last_prefetch_at=now - timedelta(hours=4))
    cold = item(storage_tier="cold", last_prefetch_at=now - timedelta(hours=4))
    old = item(last_prefetch_at=now - timedelta(hours=13))
    never_prefetched = item(last_prefetch_at=None)
    db = FakeDB(rows=[
        (protected.id, now - timedelta(hours=5)),
        (watched.id, now - timedelta(hours=3)),
    ])

    result = asyncio.run(prefetch_state.prefetch_protection_map(
        db,
        [protected, watched, cold, old, never_prefetched],
        now=now,
    ))

    assert result[protected.id] == protected.last_prefetch_at + timedelta(hours=12)
    assert result[watched.id] is None
    assert result[cold.id] is None
    assert result[old.id] is None
    assert result[never_prefetched.id] is None
    assert db.executed is True


def test_prefetch_protection_map_falls_back_to_time_grace_on_query_failure(monkeypatch):
    now = datetime(2026, 6, 12, 12, 0, 0)
    monkeypatch.setattr(prefetch_state.settings, "prefetch_grace_hours", 12)
    recently_prefetched = item(last_prefetch_at=now - timedelta(hours=1))
    db = FakeDB(error=RuntimeError("database unavailable"))

    result = asyncio.run(prefetch_state.prefetch_protection_map(db, [recently_prefetched], now=now))

    assert result[recently_prefetched.id] == recently_prefetched.last_prefetch_at + timedelta(hours=12)


def test_prefetch_protection_map_skips_db_when_no_recent_hot_prefetches(monkeypatch):
    now = datetime(2026, 6, 12, 12, 0, 0)
    monkeypatch.setattr(prefetch_state.settings, "prefetch_grace_hours", 12)
    old_hot = item(last_prefetch_at=now - timedelta(hours=13))
    recent_cold = item(storage_tier="cold", last_prefetch_at=now - timedelta(hours=1))
    db = FakeDB(error=AssertionError("query should not run"))

    result = asyncio.run(prefetch_state.prefetch_protection_map(db, [old_hot, recent_cold], now=now))

    assert result == {old_hot.id: None, recent_cold.id: None}
    assert db.executed is False
