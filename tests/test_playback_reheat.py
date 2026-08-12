from core.prefetcher import _playback_reheat_due
from models.tables import MediaItem

_TICKS_PER_SECOND = 10_000_000


def media_item(**overrides):
    import uuid
    values = {
        "id": uuid.uuid4(),
        "jellyfin_id": uuid.uuid4().hex,
        "title": "Cold Movie",
        "item_type": "movie",
        "file_size_bytes": 1024,
        "storage_tier": "cold",
        "transfer_direction": None,
        "file_path": "/media_2/Movie.mkv",
        "temperature": 10.0,
    }
    values.update(overrides)
    return MediaItem(**values)


def test_cold_item_over_threshold_is_due():
    item = media_item()
    assert _playback_reheat_due(item, 60 * _TICKS_PER_SECOND) is True


def test_cold_item_exactly_at_threshold_is_due():
    item = media_item()
    assert _playback_reheat_due(item, 60 * _TICKS_PER_SECOND) is True
    assert _playback_reheat_due(item, 60 * _TICKS_PER_SECOND - 1) is False


def test_cold_item_below_threshold_not_due():
    item = media_item()
    assert _playback_reheat_due(item, 59 * _TICKS_PER_SECOND) is False
    assert _playback_reheat_due(item, 1 * _TICKS_PER_SECOND) is False


def test_hot_item_never_due():
    item = media_item(storage_tier="hot")
    assert _playback_reheat_due(item, 10 * 60 * _TICKS_PER_SECOND) is False


def test_transferring_item_never_due():
    item = media_item(storage_tier="transferring", transfer_direction="freeze")
    assert _playback_reheat_due(item, 10 * 60 * _TICKS_PER_SECOND) is False


def test_unknown_duration_never_due():
    item = media_item()
    assert _playback_reheat_due(item, None) is False


def test_disabled_setting_never_due(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "playback_reheat_enabled", False)
    item = media_item()
    assert _playback_reheat_due(item, 10 * 60 * _TICKS_PER_SECOND) is False


def test_resume_requires_new_watching():
    # Delta is measured from session start (webhook _play_duration), so a
    # resumed session only counts NEW playback toward the threshold.
    item = media_item()
    delta_60s = 60 * _TICKS_PER_SECOND  # resumed at 45:00, watched to 46:00
    assert _playback_reheat_due(item, delta_60s) is True
    # 30s of new watching is not due.
    assert _playback_reheat_due(item, 30 * _TICKS_PER_SECOND) is False


def test_play_duration_ticks():
    from api.routes.webhook import _play_duration
    from models.schemas import PlaybackEventIn

    def evt(position_ticks):
        return PlaybackEventIn(
            jellyfin_id="abc", user_id="user1", username=None, event_type="progress",
            play_method=None, position_ticks=position_ticks, duration_ticks=None,
            client_name=None, device_name=None, item_type="episode", title=None,
            series_id=None, series_name=None, season_number=None, episode_number=None,
            file_path=None,
        )

    # Normal: start 45:00, now 45:01 → 60s of new watching
    session = {"start_ticks": 45 * 60 * _TICKS_PER_SECOND}
    assert _play_duration(session, evt(46 * 60 * _TICKS_PER_SECOND)) == 60 * _TICKS_PER_SECOND

    # Start unknown → None (cannot prove new watching)
    assert _play_duration({"start_ticks": None}, evt(100)) is None

    # Position unknown → None
    assert _play_duration(session, evt(None)) is None

    # Backward seek clamps to 0, never negative
    assert _play_duration(session, evt(44 * 60 * _TICKS_PER_SECOND)) == 0
