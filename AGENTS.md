# AGENTS.md — Frostbite

## Quick reference
- **Start**: `uvicorn api.main:app --host 0.0.0.0 --port 8000`
- **Docker**: `docker build -t frostbite . && docker run`
- **Run migrations**: `alembic upgrade head` (uses `DATABASE_URL` env var, NOT `alembic.ini`)
- **Frontend dev**: `cd frontend && npm run dev` (Vite dev server)
- **Infra context**: see `CLAUDE.md` for rclone endpoints, mergerfs layout, and K8s deployment details

## Architecture
```
api/main.py          → FastAPI app, lifespan manages singleton startup/shutdown
api/routes/          → 11 route modules (webhook, items, dashboard, transfers, series, etc.)
core/                → business logic (scorer, prefetcher, scheduler, transfer_manager, etc.)
models/tables.py     → SQLAlchemy ORM models (MediaItem, PlaybackEvent, Transfer, AppSettings, ScoreHistory)
models/schemas.py    → Pydantic response models
models/database.py   → async engine, session factory
config.py            → pydantic-settings, loads from env + .env
frontend/            → React 18 SPA (Vite, TanStack Query, Recharts, Tailwind)
```

## Settings quirks
- `config.settings` is a **mutable singleton**. `core.runtime_settings.load_overrides()` patches it in-place from `app_settings` DB rows at startup. Settings edits via the dashboard write to both DB and the in-memory object immediately (no restart needed).
- Alembic's **online mode** imports `config.settings` and uses `settings.database_url` — the `sqlalchemy.url` in `alembic.ini` is only used for offline mode. Make sure `DATABASE_URL` env var is set before running migrations.

## Route registration order is critical
`api/main.py:47` — `controls` router MUST be registered before `transfers`:
```python
app.include_router(controls.router, prefix="/api")   # before transfers — avoids UUID param shadowing
app.include_router(transfers.router, prefix="/api")
```
FastAPI matches routes in registration order. `transfers` has `{id}` path params that would swallow routes like `/api/transfers/bulk-cancel` if registered first.

## Item ID format quirk
Jellyfin webhooks send UUIDs with hyphens (e.g. `a1b2c3d4-...`), but library sync stores them as bare hex. Lookups normalize by stripping hyphens:
```python
normalized_id = event.jellyfin_id.replace("-", "")
```

## Tdarr gate
- Files with `tdarr_eligible=False` are **invisible** to scoring and freezing.
- The scheduled `sync_tdarr_eligibility()` job runs every 10 min and flips `tdarr_eligible=True` once Tdarr confirms a file is done encoding.
- Cold items already passed the gate — they stay scorable even if Tdarr drops them.

## Transfer semantics
- Transfers are **copy-then-verify-then-delete** via rclone RC — never raw moves.
- Valid extensions locked in `core/transfer_manager.py:_MEDIA_EXTENSIONS`.
- After each transfer, VFS cache is invalidated on ALL nodes via `rclone_vfs_urls`.
- `import httpx` is used inline in some places (e.g. `scheduler.py:293`) — not top-level.

## No test/lint framework
There are **no tests, no linter config, no type checker, no CI checks** beyond Docker build. If asked to add any, you are starting from scratch — pick tools, write configs, and wire them up.

## Dependencies
- `requirements.txt` uses `>=` bounds — **not pinned**.
- `frontend/package-lock.json` is **gitignored**; Dockerfile falls back to `npm install` without lockfile.
- Docker image includes rclone (installed in the build stage).
