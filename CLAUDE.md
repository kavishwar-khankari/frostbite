# CLAUDE.md

## Web search

Always delegate web searches to the `websearch` subagent via the Task tool. Example: "search the web for X and return the results". The `websearch` subagent uses a cheap DeepSeek model with SearXNG MCP tools for normal web research, BrowserMCP in connected Chrome when SearXNG is blocked or insufficient, and BrowserMCP first for Reddit. Never use `WebSearch` or `WebFetch` directly; use `Task(subagent_type="websearch", ...)` instead.

## Reading Reddit threads

Use the `websearch` subagent for Reddit research. It should use BrowserMCP in connected Chrome for Reddit search, subreddit browsing, and thread reading.

For non-Reddit sites, the `websearch` subagent should try SearXNG first. If SearXNG cannot access or adequately read a site because of 401/403/429 errors, bot checks, CAPTCHA, Cloudflare, login/session requirements, heavy JavaScript rendering, missing page content, or required interaction, it should switch to BrowserMCP in connected Chrome and report the visible state if blocked.

When using BrowserMCP, each subagent should create a fresh browser tab for its own browsing task, keep that task's browsing in that tab, and close the tab when the task completes or exits if safe.

Do not rely on direct `www.reddit.com`, `old.reddit.com`, `.json` fetches, or Reddit MCP for Reddit by default. If BrowserMCP cannot access Reddit, report the exact visible failure/login/CAPTCHA/rate-limit state and ask the user to connect Chrome or handle the gate in the browser.

## Incidents

Frostbite-specific operational incidents are tracked in `incidents/`. Read `incidents/README.md` first, then the relevant incident file.

When you solve a Frostbite incident:
1. Create `incidents/<NNN>-<slug>.md` using the next available number (check `incidents/README.md` for the last used).
2. Follow this structure: Date, Symptoms, Affected, Root Cause, Fix Steps, Prevention.
3. If the incident is a recurrence of a previous one, update the existing file instead of creating a new one.
4. Append a row to the index table in `incidents/README.md`.

---

## Project: Frostbite — Intelligent Tiered Storage Engine for Jellyfin

### What this is
Backend engine for Teapot (Jellyfin media server) that manages automatic
tiered storage between NAS (hot) and OpenDrive cloud (cold).

### Architecture
Full architecture doc: docs/teapot-architecture.md
This repo is Section 5 (Frostbite Engine) + Section 6 (Dashboard).

### Infrastructure (already running, not in this repo)
- mergerfs union mount at /mnt/merged/media (NAS + cloud)
- rclone mount (read-only, encrypted) at /mnt/cloud/media
- rclone RC daemon at 127.0.0.1:5572 (transfers)
- rclone mount RC at 127.0.0.1:5573 (VFS cache invalidation)
- NAS direct at /mnt/nas/media
- mergerfs xattr detection: getfattr -n user.mergerfs.basepath <file>

### Tech stack
- Python 3.12+, FastAPI, SQLAlchemy 2.0 + asyncpg, Alembic
- PostgreSQL 16 (deployed separately in K8s)
- APScheduler for periodic tasks
- httpx for async rclone RC calls
- WebSocket for live dashboard updates

### Key endpoints on the VM
- rclone RC (transfers): POST http://127.0.0.1:5572
- rclone RC (VFS cache): POST http://127.0.0.1:5573/vfs/forget
- Jellyfin API: https://teapot.techtronics.top
- Sonarr API: internal K8s service
- Radarr API: internal K8s service

### Deployment
- Runs as a K8s Deployment in namespace "frostbite" with hostNetwork: true
- Uses hostPath volumes for /mnt/merged/media and /mnt/nas/media
- Config via Doppler secrets + ConfigMap
- GitOps via ArgoCD

### Cloud remote
- rclone remote name: opendrive-crypt (encrypted)
- Freeze = move NAS → cloud via rclone RC sync/copy
- Reheat = copy cloud → NAS via rclone RC sync/copy
- After transfer: invalidate VFS cache via POST to :5573/vfs/forget

### Testing
- OpenDrive upload speed: ~300 KB/s to 1.5 MB/s (throttled)
- OpenDrive download speed: 3-11 MB/s (unthrottled)
- Cold file playback start: ~1-2 seconds
- Cold file seek: ~10 seconds (OpenDrive download speed limited)
