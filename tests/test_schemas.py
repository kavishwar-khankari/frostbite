import uuid
from datetime import datetime
from types import SimpleNamespace

from models.schemas import PlaybackEventIn, TransferResponse


def test_playback_event_from_flat_webhook_normalizes_ids_and_numbers():
    event = PlaybackEventIn.from_webhook({
        "ItemId": "a1b2c3d4-1111-2222-3333-444455556666",
        "UserId": "user-1",
        "NotificationUsername": "alice",
        "NotificationType": "PlaybackStart",
        "PlayMethod": "DirectPlay",
        "PositionTicks": "0",
        "RunTimeTicks": "12345",
        "ClientName": "Jellyfin Web",
        "DeviceName": "Browser",
        "ItemType": "Episode",
        "Name": "Pilot",
        "SeriesId": "series-1",
        "SeriesName": "Show",
        "SeasonNumber": "2",
        "EpisodeNumber": "not-a-number",
        "ItemPath": "/media_2/Show/S02E01.mkv",
    })

    assert event.jellyfin_id == "a1b2c3d4111122223333444455556666"
    assert event.event_type == "start"
    assert event.position_ticks is None
    assert event.duration_ticks == 12345
    assert event.item_type == "episode"
    assert event.season_number == 2
    assert event.episode_number is None
    assert event.file_path == "/media_2/Show/S02E01.mkv"


def test_playback_event_from_nested_webhook_uses_stock_payload_fallbacks():
    event = PlaybackEventIn.from_webhook({
        "NotificationType": "UnknownEvent",
        "Item": {
            "Id": "abcdef",
            "Type": "Movie",
            "Name": "Nested Movie",
            "RunTimeTicks": 999,
            "MediaSources": [{"Path": "/media_2/Movies/Nested.mkv"}],
        },
        "Session": {
            "UserId": "nested-user",
            "UserName": "bob",
            "Client": "Android TV",
            "DeviceName": "Shield",
            "PlayState": {"PlayMethod": "Transcode", "PositionTicks": 42},
        },
    })

    assert event.jellyfin_id == "abcdef"
    assert event.user_id == "nested-user"
    assert event.username == "bob"
    assert event.event_type == "unknown"
    assert event.play_method == "Transcode"
    assert event.position_ticks == 42
    assert event.duration_ticks == 999
    assert event.item_type == "movie"
    assert event.file_path == "/media_2/Movies/Nested.mkv"


def test_transfer_response_from_orm_with_item_sets_prefetch_fields():
    transfer_id = uuid.uuid4()
    media_item_id = uuid.uuid4()
    queued_at = datetime(2026, 6, 12, 12, 0, 0)
    protected_until = datetime(2026, 6, 13, 0, 0, 0)
    manual_until = datetime(2026, 6, 14, 12, 0, 0)
    transfer = SimpleNamespace(
        id=transfer_id,
        media_item_id=media_item_id,
        direction="freeze",
        trigger="auto_score",
        priority=80,
        status="queued",
        bytes_transferred=0,
        bytes_total=100,
        speed_bps=0,
        eta_seconds=None,
        error_message=None,
        queued_at=queued_at,
        started_at=None,
        completed_at=None,
    )
    item = SimpleNamespace(
        title="Episode 1",
        series_name="Show",
        season_number=1,
        item_type="episode",
        file_size_bytes=100,
        temperature=12.3,
        storage_tier="hot",
        upload_blocked=False,
        last_prefetch_at=datetime(2026, 6, 12, 8, 0, 0),
        last_manual_reheat_at=datetime(2026, 6, 12, 12, 0, 0),
    )

    response = TransferResponse.from_orm_with_item(transfer, item, protected_until, manual_until)

    assert response.id == transfer_id
    assert response.item_title == "Episode 1"
    assert response.item_prefetch_protected is True
    assert response.item_prefetch_protected_until == protected_until
    assert response.item_manual_reheat_protected is True
    assert response.item_manual_reheat_protected_until == manual_until
    assert response.item_last_manual_reheat_at == item.last_manual_reheat_at
