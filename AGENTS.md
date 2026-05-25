# AGENTS.md — Frostbite

## Project

Intelligent tiered storage engine for Teapot (Jellyfin media server) that manages automatic tiered storage between NAS (hot) and OpenDrive cloud (cold). Full architecture: `docs/teapot-architecture.md`. This repo covers Sections 5 (Engine) + 6 (Dashboard).

## Quick reference
- **Start**: `uvicorn api.main:app --host 0.0.0.0 --port 8000`
- **Docker**: `docker build -t frostbite . && docker run`
- **Run migrations**: `alembic upgrade head` (uses `DATABASE_URL` env var, NOT `alembic.ini`)
- **Frontend dev**: `cd frontend && npm run dev` (Vite dev server)

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

### Tech stack
- Python 3.12+, FastAPI, SQLAlchemy 2.0 + asyncpg, Alembic
- PostgreSQL 16 (deployed separately in K8s)
- APScheduler for periodic tasks
- httpx for async rclone RC calls
- WebSocket for live dashboard updates

## Infrastructure (already running)
- mergerfs union mount at /mnt/merged/media (NAS + cloud)
- rclone mount (read-only, encrypted) at /mnt/cloud/media
- rclone RC daemon at 127.0.0.1:5572 (transfers)
- rclone mount RC at 127.0.0.1:5573 (VFS cache invalidation)
- NAS direct at /mnt/nas/media
- mergerfs xattr detection: `getfattr -n user.mergerfs.basepath <file>`

## Key endpoints on the VM
- rclone RC (transfers): POST http://127.0.0.1:5572
- rclone RC (VFS cache): POST http://127.0.0.1:5573/vfs/forget
- Jellyfin API: https://teapot.techtronics.top
- Sonarr API: internal K8s service
- Radarr API: internal K8s service

## Deployment
- Runs as a K8s Deployment in namespace "frostbite" with hostNetwork: true
- Uses hostPath volumes for /mnt/merged/media and /mnt/nas/media
- Config via Doppler secrets + ConfigMap
- GitOps via ArgoCD

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
- Cloud remote: `opendrive-crypt` (encrypted).
- Freeze = move NAS → cloud via rclone RC sync/copy.
- Reheat = copy cloud → NAS via rclone RC sync/copy.
- After each transfer, VFS cache is invalidated on ALL nodes via POST to :5573/vfs/forget.
- `import httpx` is used inline in some places (e.g. `scheduler.py:293`) — not top-level.

## Testing benchmarks
- OpenDrive upload speed: ~300 KB/s to 1.5 MB/s (throttled)
- OpenDrive download speed: 3-11 MB/s (unthrottled)
- Cold file playback start: ~1-2 seconds
- Cold file seek: ~10 seconds (OpenDrive download speed limited)

## No test/lint framework
There are **no tests, no linter config, no type checker, no CI checks** beyond Docker build. If asked to add any, you are starting from scratch — pick tools, write configs, and wire them up.

## Dependencies
- `requirements.txt` uses `>=` bounds — **not pinned**.
- `frontend/package-lock.json` is **gitignored**; Dockerfile falls back to `npm install` without lockfile.
- Docker image includes rclone (installed in the build stage).

## Incidents
Frostbite-specific operational incidents are tracked in `incidents/`. Read `incidents/README.md` first, then the relevant incident file.

When you solve a Frostbite incident:
1. Create `incidents/<NNN>-<slug>.md` using the next available number (check `incidents/README.md` for the last used).
2. Follow this structure: Date, Symptoms, Affected, Root Cause, Fix Steps, Prevention.
3. If the incident is a recurrence of a previous one, update the existing file instead of creating a new one.
4. Append a row to the index table in `incidents/README.md`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Web search

Always delegate web searches to the `websearch` subagent via the Task tool. Example: "search the web for X and return the results". The `websearch` subagent uses the cheap `deepseek/deepseek-v4-flash` model and only has SearXNG MCP tools — this avoids the $0.02/query OpenRouter built-in search cost. Never use the built-in `WebSearch` or `WebFetch` tools directly.

## Reading Reddit threads

The new Reddit UI (`www.reddit.com`) blocks direct fetch with a verification wall. Use either of these instead:
- **JSON API**: append `.json` to the URL (e.g. `https://www.reddit.com/r/subreddit/comments/.../.json`) — use `searxng_web_url_read` with `maxLength` or `paragraphRange`.
- **Old Reddit**: replace `www.reddit.com` with `old.reddit.com` — use `searxng_web_url_read`.
