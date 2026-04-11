# Frostbite

Intelligent tiered storage engine for Jellyfin. Automatically moves media files between NAS (hot) and encrypted cloud storage (cold) based on playback activity — keeping frequently watched content local and archiving everything else to save disk space.

## How it works

Frostbite scores every media file on a temperature scale (0–100). Files cool down over time if unwatched and get frozen to cloud storage when they drop below the threshold. When someone starts playing a cold file, it reheats back to NAS. The scoring engine factors in recency, play count, unique viewers, velocity, newness, series status, and community rating.

```
NAS (hot tier) ──── score drops below 25 ────► Cloud (cold tier)
                                                        │
Cloud (cold tier) ── playback start / score > 60 ───► NAS (hot tier)
```

Files only enter the freeze cycle after [Tdarr](https://tdarr.io) has finished encoding them to AV1 — raw or in-progress encodes are never touched.

## Features

- **Automatic freeze/reheat** — rclone copy-then-verify-then-delete (never a raw move)
- **Predictive prefetch** — queues the next 3 episodes for reheat when you start watching a series
- **Tdarr gate** — only manages files that have completed AV1 encoding
- **Jellyfin webhooks** — real-time playback events drive scoring boosts
- **Emergency freeze** — triggers when NAS free space drops below threshold
- **Freeze window** — freezes only run between 00:00–08:00 IST to avoid daytime I/O
- **Live dashboard** — React SPA with WebSocket updates, temperature heatmap, transfer queue, and storage stats
- **Score breakdown** — per-item breakdown of all 8 scoring factors via hover tooltip
- **Series/season management** — bulk freeze/reheat at series or season level
- **Sonarr/Radarr metadata** — series status and monitoring state feed into scoring
- **Pause/resume controls** — pause all transfers and resume via dashboard
- **Runtime settings** — adjust thresholds, concurrency, and freeze window without restart
- **Playback history import** — full reimport from Jellyfin Playback Reporting plugin
- **Multi-node rclone** — parallel transfers across multiple cluster nodes
- **Orphan cleanup** — library sync removes stale entries when files are replaced or deleted

## Stack

| Layer | Technology |
|---|---|
| API | Python 3.12, FastAPI, uvicorn |
| Frontend | React 18, Vite, TanStack Query, Recharts, Tailwind CSS |
| Database | PostgreSQL 16, SQLAlchemy 2.0 (asyncpg), Alembic |
| Scheduling | APScheduler (AsyncIOScheduler) |
| Transfers | rclone RC daemon (multi-node) |
| Secrets | Doppler |
| Deployment | Kubernetes (RKE2) + ArgoCD |
| CI/CD | GitHub Actions → Docker Hub → ArgoCD auto-sync |

## Scoring formula

| Factor | Max | Description |
|---|---|---|
| Recency | 30 | Exponential decay since last play (half-life 14 days) |
| Play count | 20 | Log scale, saturates at ~50 plays |
| Unique viewers | 15 | Log scale, saturates at ~20 viewers |
| Trending velocity | 15 | 7-day vs 30-day play ratio |
| Newness | 30 | Full points for first 7 days, linear decay to 0 at day 30 |
| Series status | 5 | Bonus for continuing/airing series |
| Community rating | 5 | Jellyfin community rating (0–10 scale) |
| Size penalty | −5 | Files over 5 GB get penalized |

## Architecture

```
Jellyfin ──webhook──► Frostbite API ◄── React Dashboard (SPA)
                            │                    ▲
                     ┌──────┴──────┐             │
                  Scorer      Prefetcher     WebSocket
                     │              │
               Scheduler      Transfer Worker
                     │              │
               PostgreSQL     rclone RC daemon (multi-node)
                                    │
                          NAS ◄────► OpenDrive (encrypted)

Infrastructure:
  mergerfs ─── union mount (NAS + cloud read-only)
  rclone  ─── encrypted remote + VFS cache invalidation
  Tdarr   ─── AV1 encoding gate (Intel QSV)
```

## API

| Endpoint | Method | Description |
|---|---|---|
| `/healthz` | GET | Health check |
| `/webhook/jellyfin` | POST | Jellyfin webhook receiver |
| `/ws` | WS | Live dashboard updates |
| `/api/dashboard` | GET | Aggregated stats |
| `/api/items` | GET | Media items with filtering, sorting, pagination |
| `/api/items/{id}/score-breakdown` | GET | Per-factor temperature breakdown |
| `/api/items/{id}/temperature` | PATCH | Override item temperature |
| `/api/series` | GET | Series/season aggregation |
| `/api/transfers` | GET | Transfer queue with filtering |
| `/api/transfers/{id}/cancel` | POST | Cancel a transfer |
| `/api/transfers/{id}/retry` | POST | Retry failed transfer |
| `/api/transfers/bulk-cancel` | POST | Bulk cancel transfers |
| `/api/transfers/bulk-retry` | POST | Bulk retry transfers |
| `/api/transfers/pause-all` | POST | Pause transfer worker |
| `/api/transfers/resume` | POST | Resume transfer worker |
| `/api/freeze` | POST | Manual freeze single item |
| `/api/reheat` | POST | Manual reheat single item |
| `/api/bulk-freeze` | POST | Bulk freeze by IDs |
| `/api/bulk-reheat` | POST | Bulk reheat by IDs |
| `/api/freeze-series` | POST | Freeze entire series/season |
| `/api/reheat-series` | POST | Reheat entire series/season |
| `/api/settings` | GET/PUT | Runtime settings |
| `/api/score-history` | GET | Historical stats (up to 90 days) |
| `/api/sync/library` | POST | Trigger full library sync |
| `/api/scoring/run` | POST | Trigger scoring sweep |
| `/api/tdarr/sync` | POST | Trigger Tdarr eligibility sync |
| `/api/playback/import-history` | POST | Reimport Jellyfin playback history |

## Configuration

All settings are environment variables injected via Doppler:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `JELLYFIN_URL` | Jellyfin server URL |
| `JELLYFIN_API_KEY` | Jellyfin API key |
| `SONARR_URL` / `SONARR_API_KEY` | Sonarr connection |
| `RADARR_URL` / `RADARR_API_KEY` | Radarr connection |
| `TDARR_URL` / `TDARR_API_KEY` | Tdarr connection |
| `RCLONE_RC_URL` | rclone RC daemon URL |
| `RCLONE_REMOTE` | rclone remote name (default: `opendrive-crypt`) |

Runtime-adjustable thresholds (editable via dashboard):

| Setting | Default |
|---|---|
| `FREEZE_THRESHOLD` | 25.0 |
| `REHEAT_THRESHOLD` | 60.0 |
| `PREFETCH_BOOST` | +40.0 pts |
| `MAX_CONCURRENT_REHEATS` | 2 |
| `MAX_CONCURRENT_FREEZES` | 2 |
| `FREEZE_WINDOW_START` | 00:00 IST |
| `FREEZE_WINDOW_END` | 08:00 IST |
| `EMERGENCY_FREEZE_THRESHOLD_GB` | 15 GB |

## Deployment

Runs as a Kubernetes Deployment in namespace `frostbite` with `hostNetwork: true` for rclone RC access on `127.0.0.1:5572/5573`. Secrets injected via Doppler operator. GitOps via ArgoCD from [kubernetes-homelab](https://github.com/kavishwar-khankari/kubernetes-homelab).

CI pushes to Docker Hub on every main branch commit and auto-updates the K8s manifest, triggering ArgoCD sync.

---

Part of the **Teapot** homelab media stack.
