import asyncio

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.main import app
from core import runtime_settings
from models.tables import AppSettings


def test_disabling_playback_reheat_is_saved_and_returned(monkeypatch):
    """Given reheat is on, when disabled via the API, then it remains off after reloading."""
    monkeypatch.setattr(runtime_settings.settings, "playback_reheat_enabled", True)

    async def check_journey():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(runtime_settings, "async_session_factory", sessions)

        try:
            async with engine.begin() as connection:
                await connection.run_sync(AppSettings.__table__.create)

            # ASGITransport exercises the real routes without starting the scheduler.
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                before = await client.get("/api/settings")
                assert before.status_code == 200
                assert before.json()["playback_reheat_enabled"] is True

                updated = await client.put(
                    "/api/settings",
                    json={"key": "playback_reheat_enabled", "value": False},
                )
                assert updated.status_code == 200
                assert updated.json()["playback_reheat_enabled"] is False

                async with sessions() as db:
                    saved = await db.get(AppSettings, "playback_reheat_enabled")
                    assert saved is not None
                    assert saved.value == "False"

                # Simulate a fresh process reading the persisted override.
                runtime_settings.settings.playback_reheat_enabled = True
                await runtime_settings.load_overrides()

                after = await client.get("/api/settings")
                assert after.status_code == 200
                assert after.json()["playback_reheat_enabled"] is False
        finally:
            await engine.dispose()

    asyncio.run(check_journey())
