from contextlib import asynccontextmanager

from fastapi import FastAPI

import api.deps as deps
from api.routes import controls, dashboard, items, status, transfers, webhook, ws
from core.jellyfin_client import JellyfinClient
from core.scheduler import start_scheduler, stop_scheduler
from core.tdarr_client import TdarrClient
from core.transfer_manager import TransferManager
from models.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise singleton clients — must happen before any request is served
    deps._jellyfin_client = JellyfinClient()
    deps._transfer_manager = TransferManager()

    await start_scheduler()
    yield
    await stop_scheduler()
    await engine.dispose()


app = FastAPI(
    title="Frostbite",
    description="Intelligent tiered storage engine for Jellyfin / Teapot",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook.router)
app.include_router(items.router, prefix="/api")
app.include_router(status.router, prefix="/api")
app.include_router(transfers.router, prefix="/api")
app.include_router(controls.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(ws.router)


@app.get("/healthz")
async def health() -> dict:
    return {"ok": True}
