import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  [%(name)s] %(message)s",
)

import api.deps as deps
from api.routes import controls, dashboard, items, score_history, series, settings, status, transfers, webhook, ws
from core.jellyfin_client import JellyfinClient
from core.runtime_settings import load_overrides
from core.scheduler import start_scheduler, stop_scheduler
from core.transfer_manager import TransferManager
from models.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise singleton clients — must happen before any request is served
    deps._jellyfin_client = JellyfinClient()
    deps._transfer_manager = TransferManager()

    await load_overrides()
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
app.include_router(series.router, prefix="/api")
app.include_router(score_history.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(ws.router)


@app.get("/healthz")
async def health() -> dict:
    return {"ok": True}


# Serve the React SPA — must be last so API routes take precedence
_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
