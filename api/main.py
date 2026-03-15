import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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


# Serve the React SPA — assets are mounted at /assets, everything else falls through to index.html
_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_assets_dir = os.path.join(_static_dir, "assets")
if os.path.isdir(_assets_dir):
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="static_assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    index = os.path.join(_static_dir, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    raise HTTPException(status_code=404)
