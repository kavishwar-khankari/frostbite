from datetime import datetime, timedelta, timezone

import pytest

from core import scorer
from core.scorer import ItemMeta, PlaybackStats


class FixedDateTime:
    @classmethod
    def utcnow(cls):
        return datetime(2026, 6, 12, 12, 0, 0)


def test_temperature_breakdown_combines_hot_signals_and_clamps(monkeypatch):
    now = FixedDateTime.utcnow()
    monkeypatch.setattr(scorer, "datetime", FixedDateTime)

    score, breakdown = scorer.calculate_temperature_with_breakdown(
        ItemMeta(
            file_size_bytes=8 * 1024**3,
            date_added=now - timedelta(days=2),
            series_status="continuing",
            community_rating=8.0,
        ),
        PlaybackStats(
            last_played_at=now - timedelta(days=14),
            total_plays=50,
            unique_viewers=20,
            plays_last_7d=5,
            plays_last_30d=20,
        ),
    )

    assert score == 100.0
    assert breakdown == {
        "recency": 15.0,
        "play_count": 20.0,
        "unique_viewers": 15.0,
        "trending": 15.0,
        "newness": 30.0,
        "series_status": 5.0,
        "community_rating": 4.0,
        "size_penalty": -1.5,
    }


def test_temperature_never_goes_below_zero(monkeypatch):
    monkeypatch.setattr(scorer, "datetime", FixedDateTime)

    score, breakdown = scorer.calculate_temperature_with_breakdown(
        ItemMeta(
            file_size_bytes=20 * 1024**3,
            date_added=FixedDateTime.utcnow() - timedelta(days=90),
            series_status="ended",
            community_rating=None,
        ),
        PlaybackStats(
            last_played_at=None,
            total_plays=0,
            unique_viewers=0,
            plays_last_7d=0,
            plays_last_30d=0,
        ),
    )

    assert score == 0.0
    assert breakdown["size_penalty"] == -5.0


def test_aware_datetimes_are_normalized_to_utc(monkeypatch):
    monkeypatch.setattr(scorer, "datetime", FixedDateTime)
    ist = timezone(timedelta(hours=5, minutes=30))

    _, breakdown = scorer.calculate_temperature_with_breakdown(
        ItemMeta(
            file_size_bytes=1024,
            date_added=None,
            series_status=None,
            community_rating=None,
        ),
        PlaybackStats(
            last_played_at=datetime(2026, 6, 11, 17, 30, 0, tzinfo=ist),
            total_plays=0,
            unique_viewers=0,
            plays_last_7d=0,
            plays_last_30d=0,
        ),
    )

    assert breakdown["recency"] == pytest.approx(28.6, abs=0.1)
