import asyncio
import uuid

from core import deletion_manager, transfer_manager
from models.tables import MediaItem, Transfer


class SingleValueResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value



class FakeDB:
    def __init__(self, item):
        self.item = item

    async def execute(self, statement):
        return SingleValueResult(self.item)


def media_item(**overrides):
    values = {
        "id": uuid.uuid4(),
        "jellyfin_id": uuid.uuid4().hex,
        "title": "Movie",
        "item_type": "movie",
        "file_size_bytes": 1024,
        "storage_tier": "hot",
        "transfer_direction": None,
        "file_path": "/media_2/Movie.mkv",
    }
    values.update(overrides)
    return MediaItem(**values)


def transfer(**overrides):
    values = {
        "id": uuid.uuid4(),
        "media_item_id": uuid.uuid4(),
        "direction": "freeze",
        "trigger": "manual",
        "priority": 50,
        "status": "queued",
        "source_path": "Movies/Movie.mkv",
        "dest_path": "Movies/Movie.mkv",
        "error_message": None,
        "completed_at": None,
    }
    values.update(overrides)
    return Transfer(**values)


def test_execute_transfer_rejects_non_media_extensions():
    t = transfer(source_path="Movies/Movie.nfo", dest_path="Movies/Movie.nfo")

    asyncio.run(transfer_manager._execute_transfer(FakeDB(media_item()), t))

    assert t.status == "failed"
    assert "not a permitted media extension" in t.error_message


def test_execute_transfer_rejects_long_cloud_filenames():
    filename = f"{'a' * 121}.mkv"
    t = transfer(source_path=f"Movies/{filename}", dest_path=f"Movies/{filename}")

    asyncio.run(transfer_manager._execute_transfer(FakeDB(media_item()), t))

    assert t.status == "failed"
    assert "Filename too long" in t.error_message


def test_execute_transfer_normalizes_absolute_legacy_paths_before_preflight(monkeypatch):
    t = transfer(source_path="/media_2/Movies/Movie.mkv", dest_path="/media_2/Movies/Movie.mkv")
    monkeypatch.setattr(transfer_manager.settings, "jellyfin_media_root", "/media_2")
    monkeypatch.setattr(transfer_manager.settings, "nas_root", "/mnt/nas/media")

    async def cloud_missing(rel_path, size):
        return False

    monkeypatch.setattr(transfer_manager, "_quick_cloud_check", cloud_missing)
    monkeypatch.setattr(transfer_manager.os.path, "isfile", lambda path: False)

    asyncio.run(transfer_manager._execute_transfer(FakeDB(media_item()), t))

    assert t.source_path == "Movies/Movie.mkv"
    assert t.dest_path == "Movies/Movie.mkv"
    assert t.status == "failed"
    assert t.error_message == "Source file not found on NAS: /mnt/nas/media/Movies/Movie.mkv"


class FakeResponse:
    def json(self):
        return {}


class FakeAsyncClient:
    def __init__(self, requests):
        self.requests = requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json):
        self.requests.append((url, json))
        return FakeResponse()


def test_vfs_invalidation_forgets_file_and_parent_directories(monkeypatch):
    requests = []
    monkeypatch.setattr(transfer_manager.settings, "rclone_vfs_urls", "http://node-a:5573")
    monkeypatch.setattr(
        transfer_manager.httpx,
        "AsyncClient",
        lambda **_: FakeAsyncClient(requests),
    )

    asyncio.run(transfer_manager._refresh_vfs_cache("series/anime/Show/Season 01/Episode.mkv"))

    assert requests[0] == (
        "http://node-a:5573/vfs/forget",
        {
            "file": "series/anime/Show/Season 01/Episode.mkv",
            "dir": "series/anime/Show/Season 01",
            "dir2": "series/anime/Show",
        },
    )


def test_deletion_invalidation_forgets_file_and_parent_directories(monkeypatch):
    requests = []
    monkeypatch.setattr(deletion_manager.settings, "rclone_vfs_urls", "http://node-a:5573")
    monkeypatch.setattr(
        deletion_manager.httpx,
        "AsyncClient",
        lambda **_: FakeAsyncClient(requests),
    )

    asyncio.run(deletion_manager._invalidate_vfs("series/anime/Show/Season 01/Episode.mkv"))

    assert requests[0] == (
        "http://node-a:5573/vfs/forget",
        {
            "file": "series/anime/Show/Season 01/Episode.mkv",
            "dir": "series/anime/Show/Season 01",
            "dir2": "series/anime/Show",
        },
    )
