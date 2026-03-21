# Frostbite                         
                                                                                                                                                                    
    Intelligent tiered storage engine for Jellyfin. Automatically moves media files between NAS (hot) and cloud storage (cold) based on playback activity — keeping 
    frequently watched content local and archiving everything else to save disk space.                                                                              
                                                                                                                                                                    
    ## How it works                                                                                                                                                 
                                                                                                                                                                    
    Frostbite scores every media file on a temperature scale (0–100). Files cool down over time if unwatched and get frozen to cloud storage when they drop below   
    the threshold. When someone starts playing a cold file, it reheats back to NAS. The scoring engine factors in recency, play count, unique viewers, velocity,    
    newness, series status, and community rating.                                                                                                                   
                                                                                                                                                                    
    NAS (hot tier) ──── score drops below 25 ────► Cloud (cold tier)
                                                            │                                                                                                       
    Cloud (cold tier) ── playback start / score > 60 ───► NAS (hot tier)                                                                                            
                                                                                                                                                                    
    Files only enter the freeze cycle after [Tdarr](https://tdarr.io) has finished encoding them to AV1 — raw or in-progress encodes are never touched.             

    ## Features

    - **Automatic freeze/reheat** — rclone copy-then-verify-then-delete (never a raw move)
    - **Predictive prefetch** — queues the next 3 episodes for reheat when you start watching a series
    - **Tdarr gate** — only manages files that have completed AV1 encoding
    - **Jellyfin webhooks** — real-time playback events drive scoring boosts
    - **Emergency freeze** — triggers when NAS free space drops below 15 GB
    - **Freeze window** — freezes only run between 00:00–08:00 IST to avoid daytime I/O
    - **Live dashboard** — WebSocket-powered UI with heatmap, transfer queue, and storage stats
    - **Sonarr/Radarr metadata** — series status and monitoring state feed into scoring

    ## Stack

    | Layer | Technology |
    |---|---|
    | API | FastAPI + uvicorn |
    | Database | PostgreSQL 16 + SQLAlchemy 2.0 (asyncpg) |
    | Migrations | Alembic |
    | Scheduling | APScheduler (AsyncIOScheduler) |
    | Transfers | rclone RC daemon |
    | Secrets | Doppler |
    | Deployment | Kubernetes (RKE2) + ArgoCD |
    | CI | GitHub Actions → Docker Hub |

    ## Scoring formula

    | Factor | Max points |
    |---|---|
    | Recency (days since last play) | 30 |
    | Play count | 20 |
    | Unique viewers | 15 |
    | Play velocity (last 7 days) | 15 |
    | Newness (date added) | 10 |
    | Series status (continuing vs ended) | 5 |
    | Community rating | 5 |
    | File size penalty (> 5 GB) | −5 |

    ## Architecture

    Jellyfin ──webhook──► Frostbite API
                                │
                         ┌──────┴──────┐
                      Scorer      Prefetcher
                         │              │
                   Scheduler      Transfer Queue
                         │              │
                   PostgreSQL     rclone RC daemon
                                        │
                              NAS ◄──── ► OpenDrive (encrypted)

    ## Deployment

    Runs as a Kubernetes `Deployment` in namespace `frostbite` with `hostNetwork: true` so it can reach the rclone RC daemon on the host at `127.0.0.1:5572/5573`.
    Secrets are injected via the Doppler operator. GitOps via ArgoCD from the [kubernetes-homelab](https://github.com/kavishwar-khankari/kubernetes-homelab) repo.

    ## Configuration

    All settings are environment variables (injected via Doppler):

    | Variable | Description |
    |---|---|
    | `DATABASE_URL` | PostgreSQL connection string |
    | `JELLYFIN_API_KEY` | Jellyfin API key |
    | `SONARR_API_KEY` | Sonarr API key |
    | `RADARR_API_KEY` | Radarr API key |

    Key thresholds (hardcoded defaults, overridable via env):

    | Setting | Default |
    |---|---|
    | `FREEZE_THRESHOLD` | 25.0 |
    | `REHEAT_THRESHOLD` | 60.0 |
    | `PREFETCH_BOOST` | +40.0 pts |
    | `EMERGENCY_FREEZE_THRESHOLD_GB` | 15 GB |

    ## API

    | Endpoint | Description |
    |---|---|
    | `GET /healthz` | Health check |
    | `POST /webhook/jellyfin` | Jellyfin webhook receiver |
    | `GET /api/dashboard` | Aggregated stats |
    | `GET /api/items` | All media items with scores |
    | `GET /api/transfers` | Transfer queue |
    | `POST /api/transfers/manual` | Manually freeze or reheat a file |
    | `WS /ws` | Live dashboard updates |

    ---

    Part of the **Teapot** homelab media stack.