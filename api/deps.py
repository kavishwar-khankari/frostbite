from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.jellyfin_client import JellyfinClient
from core.transfer_manager import TransferManager
from models.database import async_session_factory

# ── Database session ──────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db)]

# ── Singleton clients (created once at startup, reused per request) ───────────
# These are set by the lifespan in main.py after startup.

_jellyfin_client: JellyfinClient | None = None
_transfer_manager: TransferManager | None = None


def get_jellyfin_client() -> JellyfinClient:
    assert _jellyfin_client is not None, "JellyfinClient not initialised"
    return _jellyfin_client


def get_transfer_manager() -> TransferManager:
    assert _transfer_manager is not None, "TransferManager not initialised"
    return _transfer_manager


JellyfinDep = Annotated[JellyfinClient, Depends(get_jellyfin_client)]
TransferDep = Annotated[TransferManager, Depends(get_transfer_manager)]
