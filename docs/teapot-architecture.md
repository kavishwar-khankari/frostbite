# Teapot — Intelligent Tiered Storage for Jellyfin

## Architecture Document v1.0 — March 2026

---

## 1. Vision

Teapot is an intelligent tiered storage system that transparently extends PICO's Jellyfin media library beyond physical NAS capacity by using OpenDrive cloud storage as a cold tier. It provides:

- A **unified media library** visible to Jellyfin (and Sonarr/Radarr) regardless of where files physically reside
- **Live scoring** of every media file's "hotness" based on playback patterns, popularity, recency, and predictions
- **Predictive prefetching** — when a user plays S01E05, the next 3 episodes automatically warm up
- **Custom Jellyfin UI** — cold-stored content shows visual indicators, real-time download progress on playback, and manual "warm up" buttons
- A **dashboard** for PICO to monitor the full system: hotness heatmaps, transfer queues, storage utilization, and per-file status

The name "Teapot" matches the Jellyfin server name. The project codename for the scoring/tiering subsystem is **Frostbite**.

---

## 2. Infrastructure Context

| Component | Detail |
|---|---|
| Proxmox Host | 1TB SSD, kernel 6.17.9-1-pve |
| RKE2 VM | Ubuntu 24.04, 3-node HA, kernel 6.14.0-1012-intel |
| GPU | Intel Arc B570 (BMG-G21, xe driver), passthrough to VM |
| NAS | 8-10TB usable, accessed via SMB CSI |
| Internet | 300 Mbps FTTH symmetric (Pune, India) |
| Cloud | OpenDrive Personal Unlimited ($9.95/mo), >10TB stored (upload throttled, downloads unthrottled) |
| GitOps | ArgoCD, Doppler secrets, Longhorn storage |
| Existing Apps | Jellyfin, Tdarr, Sonarr, Radarr, Prowlarr, qBittorrent+Gluetun, Overseerr |
| Target Audience | Semi-public, invite-based, 50-100 users |

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     JELLYFIN CLIENTS                        │
│              (Web, Android, iOS, TV apps)                   │
│         Custom JS: cold badges, progress overlay,           │
│         warm-up button, Frostbite API calls                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   KUBERNETES (RKE2)                          │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  Jellyfin    │  │  Sonarr /    │  │  Tdarr             │  │
│  │  (teapot)    │  │  Radarr      │  │  (AV1 encode)      │  │
│  │  webhook ──────►│              │  │                    │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘  │
│         │                 │                   │              │
│         │    All see /mnt/merged/media via hostPath          │
│         │                 │                   │              │
│  ┌──────▼─────────────────▼───────────────────▼───────────┐  │
│  │              FROSTBITE ENGINE                           │  │
│  │         (frostbite namespace)                           │  │
│  │                                                         │  │
│  │  ┌─────────────┐ ┌────────────┐ ┌───────────────────┐  │  │
│  │  │ FastAPI      │ │ Scorer     │ │ Transfer Manager  │  │  │
│  │  │ (webhook rx, │ │ (live temp │ │ (rclone move/copy │  │  │
│  │  │  REST API,   │ │  calc,     │ │  via rclone rc,   │  │  │
│  │  │  WebSocket)  │ │  prefetch) │ │  progress track)  │  │  │
│  │  └──────┬───────┘ └─────┬──────┘ └────────┬──────────┘  │  │
│  │         │               │                 │             │  │
│  │  ┌──────▼───────────────▼─────────────────▼──────────┐  │  │
│  │  │              PostgreSQL 16                         │  │  │
│  │  │   (media_items, scores, transfers, events)         │  │  │
│  │  └───────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │           FROSTBITE DASHBOARD                           │  │
│  │      React + TypeScript + Vite + TailwindCSS            │  │
│  │   (frostbite-dashboard.techtronics.top)                 │  │
│  │   Hotness heatmap, transfer queue, storage stats,       │  │
│  │   per-file detail, manual controls                      │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  VM LEVEL (Ubuntu 24.04)                      │
│                                                              │
│  /mnt/nas/media/       ← SMB mount (NAS, 8-10TB, RW)        │
│  /mnt/cloud/media/     ← rclone mount (OpenDrive, RO)       │
│  /mnt/merged/media/    ← mergerfs union (what K8s sees)      │
│                                                              │
│  systemd services:                                           │
│    rclone-mount.service    (rclone mount + VFS cache)        │
│    rclone-rcd.service      (rclone RC daemon for transfers)  │
│    mergerfs-media.service  (mergerfs union mount)            │
└──────────────────────────────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   OpenDrive     │
              │  (cold storage) │
              │  "unlimited"    │
              └─────────────────┘
```

---

## 4. Layer 1 — VM Storage Infrastructure

### 4.1 Mount Hierarchy

All three mounts are managed by systemd with explicit ordering dependencies.

```
# Boot order:
1. smb-nas.mount          → /mnt/nas/media
2. rclone-mount.service   → /mnt/cloud/media
3. mergerfs-media.service → /mnt/merged/media   (After=1,2)
4. rclone-rcd.service     → localhost:5572       (After=2)
```

### 4.2 SMB NAS Mount

Already exists in PICO's setup. The existing SMB CSI PVs that Jellyfin/Sonarr/Radarr use today will be **replaced** by a hostPath pointing to the mergerfs union. This is the one breaking change.

```
# /etc/fstab (or systemd .mount unit)
//nas.local/media  /mnt/nas/media  cifs  credentials=/etc/smbcreds,uid=1000,gid=1000,iocharset=utf8,vers=3.0  0  0
```

### 4.3 rclone Mount (Cloud Read Path)

This mount is **read-only**. It exists purely so mergerfs (and therefore Jellyfin) can see cloud-stored files. All writes to cloud go through the rclone RC daemon (Section 4.4), not through this mount.

```ini
# /etc/systemd/system/rclone-mount.service
[Unit]
Description=rclone mount for OpenDrive (read-only, Jellyfin cloud tier)
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStartPre=/bin/mkdir -p /mnt/cloud/media
ExecStart=/usr/bin/rclone mount opendrive:media /mnt/cloud/media \
  --read-only \
  --allow-other \
  --vfs-cache-mode full \
  --vfs-cache-max-size 80G \
  --vfs-cache-max-age 48h \
  --vfs-read-chunk-size 64M \
  --vfs-read-chunk-size-limit 0 \
  --vfs-fast-fingerprint \
  --buffer-size 128M \
  --dir-cache-time 72h \
  --poll-interval 0 \
  --attr-timeout 1h \
  --cache-dir /var/cache/rclone \
  --log-level INFO \
  --log-file /var/log/rclone-mount.log \
  --umask 022
ExecStop=/bin/fusermount -uz /mnt/cloud/media
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Key tuning decisions:**

| Flag | Value | Rationale |
|---|---|---|
| `--vfs-cache-mode full` | full | Buffers entire files to local disk before serving; needed for Jellyfin seeking |
| `--vfs-cache-max-size 80G` | 80G | Reserve 80GB of VM disk for VFS cache. Enough for ~30-40 AV1 movies simultaneously. Adjust based on VM disk capacity. |
| `--vfs-cache-max-age 48h` | 48h | Auto-evict cached files after 48h. Prevents disk fill. |
| `--vfs-read-chunk-size 64M` | 64M | First read downloads 64MB, then doubles. At 300 Mbps (≈37 MB/s), 64MB downloads in ~1.7s — fast enough for playback to begin. |
| `--dir-cache-time 72h` | 72h | Cache directory listings aggressively. Cloud dirs change infrequently (only when Frostbite moves files). |
| `--poll-interval 0` | 0 (disabled) | Don't poll OpenDrive for changes. Frostbite controls all mutations and will invalidate cache via `rclone rc vfs/forget` when needed. |
| `--read-only` | — | Critical. Prevents accidental writes through the mount. All cloud writes go through rclone RC daemon. |
| `--attr-timeout 1h` | 1h | Cache file attributes (size, mtime) for 1h. Reduces API calls during library scans. |

**VFS cache disk location:** `/var/cache/rclone` should ideally be on fast storage (SSD). If the VM's OS disk is the Proxmox SSD, this is fine. Monitor with `du -sh /var/cache/rclone`.

### 4.4 rclone RC Daemon (Cloud Write Path)

A separate rclone instance running in daemon mode, exposing the RC API. Frostbite's Transfer Manager uses this to execute `sync/move`, `sync/copy`, and `operations/delete` commands with full progress tracking.

```ini
# /etc/systemd/system/rclone-rcd.service
[Unit]
Description=rclone remote control daemon for Frostbite transfers
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/rclone rcd \
  --rc-addr 127.0.0.1:5572 \
  --rc-no-auth \
  --transfers 2 \
  --checkers 4 \
  --log-level INFO \
  --log-file /var/log/rclone-rcd.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Why a separate daemon?** Running `rclone move` as subprocesses is fragile — if Frostbite restarts, orphan rclone processes linger. The RC daemon is persistent, and transfers survive Frostbite pod restarts. Frostbite submits async jobs and polls `core/stats` for progress.

**Access from K8s:** The rclone RC daemon listens on `127.0.0.1:5572` on the VM. Frostbite's pod accesses it via `hostNetwork: true` or a NodePort service. Since Frostbite needs hostPath access to `/mnt/merged/media` anyway, `hostNetwork: true` is the cleaner option.

**Key RC endpoints used by Frostbite:**

| Endpoint | Purpose |
|---|---|
| `sync/move` | Move file from NAS → OpenDrive (freeze) |
| `sync/copy` | Copy file from OpenDrive → NAS (reheat) |
| `operations/delete` | Delete cloud copy after confirmed reheat |
| `core/stats` | Get transfer progress (bytes, speed, ETA) |
| `job/status` | Check async job status by job ID |
| `job/stop` | Cancel a transfer |
| `vfs/forget` | Invalidate rclone mount cache after transfer |

### 4.5 mergerfs Union Mount

```ini
# /etc/systemd/system/mergerfs-media.service
[Unit]
Description=mergerfs union of NAS and cloud media
After=mnt-nas-media.mount rclone-mount.service
Requires=mnt-nas-media.mount rclone-mount.service

[Service]
Type=forking
ExecStartPre=/bin/mkdir -p /mnt/merged/media
ExecStart=/usr/bin/mergerfs \
  /mnt/nas/media:/mnt/cloud/media \
  /mnt/merged/media \
  -o defaults,allow_other,use_ino \
  -o category.create=epff \
  -o category.search=ff \
  -o category.action=all \
  -o cache.files=auto-full \
  -o cache.entry=3600 \
  -o cache.attr=3600 \
  -o cache.negative_entry=60 \
  -o cache.readdir=true \
  -o dropcacheonclose=true \
  -o moveonenospc=true \
  -o minfreespace=20G \
  -o xattr=passthrough \
  -o statfs=base \
  -o fsname=teapot-media
ExecStop=/bin/fusermount -uz /mnt/merged/media
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**Policy decisions:**

| Policy | Value | Rationale |
|---|---|---|
| `create=epff` | Existing Path, First Found | New files go to NAS (listed first) if the parent directory exists there. Since Sonarr creates series folders on NAS, new episodes land on NAS. Cloud files only exist because Frostbite moved them there. |
| `search=ff` | First Found | Reads check NAS first, then cloud. Since NAS is local, hot files (on NAS) are found with zero latency. |
| `action=all` | All branches | Deletes/renames apply to all branches. If Sonarr deletes a file, it's removed from whichever branch has it. |
| `cache.entry=3600` | 1 hour | Cache directory entries for 1h. Massively reduces `stat()` calls to rclone mount during Jellyfin library scans. |
| `cache.readdir=true` | enabled | Cache `readdir` results in kernel. Critical for large library browsing performance. |
| `moveonenospc=true` | enabled | If NAS is full during a write, mergerfs automatically moves the write to the next branch (cloud). Safety net. |
| `minfreespace=20G` | 20GB | Keep 20GB free on NAS for Tdarr cache, Jellyfin transcoding temp, etc. |
| `xattr=passthrough` | passthrough | Required for Frostbite to use `user.mergerfs.fullpath` / `user.mergerfs.basepath` xattrs to detect which branch a file is on. |

**How Frostbite detects hot vs cold:**

```python
import os, xattr

def get_storage_tier(merged_path: str) -> str:
    """Returns 'hot' if file is on NAS, 'cold' if on cloud."""
    try:
        basepath = xattr.getxattr(merged_path, b"user.mergerfs.basepath").decode()
        if basepath.startswith("/mnt/nas"):
            return "hot"
        elif basepath.startswith("/mnt/cloud"):
            return "cold"
    except OSError:
        return "unknown"
```

This is zero-cost — no database lookup, no API call. Just a single xattr syscall.

### 4.6 hostPath Exposure to Kubernetes

All pods that need media access mount the mergerfs union point:

```yaml
# In each pod spec that needs media access:
volumes:
  - name: media
    hostPath:
      path: /mnt/merged/media
      type: Directory
volumeMounts:
  - name: media
    mountPath: /media        # or wherever the app expects it
```

**Migration from SMB CSI:** Currently, Jellyfin/Sonarr/Radarr use SMB CSI PVs to access the NAS directly. These need to be changed to hostPath mounts pointing at `/mnt/merged/media`. This is a one-time manifest change per app. The apps see the exact same directory structure — the only difference is that the underlying storage is now a mergerfs union instead of a direct SMB mount.

**Tdarr special consideration:** Tdarr should **only** watch the NAS subtree for encoding, not the merged path. If Tdarr picks up a cold file from the cloud tier, it would download the entire file through rclone just to analyze it. Two options:
1. Tdarr watches `/mnt/nas/media` directly via a separate hostPath (not the merged mount)
2. Frostbite tags cloud files in Tdarr (via Tdarr's API) as "not for processing"

Option 1 is simpler and recommended.

---

## 5. Layer 2 — Frostbite Engine (Backend)

### 5.1 Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| Language | Python 3.12+ | Fast iteration on scoring model, excellent async (asyncio), rich ecosystem |
| Framework | FastAPI | Native async, WebSocket support, auto OpenAPI docs, Pydantic validation |
| Database | PostgreSQL 16 | LISTEN/NOTIFY for real-time events, JSONB for flexible metadata, robust |
| ORM | SQLAlchemy 2.0 + asyncpg | Async PostgreSQL driver, modern SQLAlchemy with type hints |
| Migrations | Alembic | Standard for SQLAlchemy |
| Task Queue | PostgreSQL LISTEN/NOTIFY + in-memory asyncio queue | No Redis needed. PG handles persistence, asyncio handles in-flight work. |
| WebSocket | FastAPI built-in | Push live score updates and transfer progress to dashboard |
| Container | python:3.12-slim + rclone binary | Needs rclone CLI for `rclone rc` calls to the host daemon |
| Scheduling | APScheduler (async) | For periodic scoring sweeps, NAS space monitoring, stale transfer cleanup |

### 5.2 Application Structure

```
frostbite/
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, lifespan, middleware
│   ├── routes/
│   │   ├── webhook.py          # POST /webhook/jellyfin — receives Jellyfin events
│   │   ├── items.py            # GET /api/items — list items with scores
│   │   ├── status.py           # GET /api/status/{item_id} — hot/cold/transferring
│   │   ├── transfers.py        # GET/POST /api/transfers — queue, progress, cancel
│   │   ├── controls.py         # POST /api/reheat, /api/freeze — manual actions
│   │   ├── dashboard.py        # GET /api/dashboard — aggregate stats for UI
│   │   └── ws.py               # WebSocket /ws — live updates to dashboard
│   └── deps.py                 # Dependency injection (db session, rclone client)
├── core/
│   ├── scorer.py               # Temperature scoring engine
│   ├── prefetcher.py           # Predictive prefetch logic
│   ├── transfer_manager.py     # rclone RC integration, queue management
│   ├── filesystem.py           # mergerfs xattr queries, file discovery
│   ├── jellyfin_client.py      # Jellyfin REST API client (metadata, users)
│   ├── sonarr_client.py        # Sonarr API client (series status)
│   ├── radarr_client.py        # Radarr API client (movie status)
│   └── scheduler.py            # Periodic tasks (sweep, space check, cleanup)
├── models/
│   ├── __init__.py
│   ├── database.py             # SQLAlchemy engine, session factory
│   ├── tables.py               # All SQLAlchemy table models
│   └── schemas.py              # Pydantic request/response schemas
├── config.py                   # Settings from env vars / Doppler
├── Dockerfile
└── requirements.txt
```

### 5.3 PostgreSQL Schema

```sql
-- Core item tracking
CREATE TABLE media_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jellyfin_id     VARCHAR(64) UNIQUE NOT NULL,      -- Jellyfin's internal item ID
    title           TEXT NOT NULL,
    item_type       VARCHAR(20) NOT NULL,              -- 'movie', 'episode', 'season', 'series'
    series_id       VARCHAR(64),                       -- Jellyfin series ID (NULL for movies)
    series_name     TEXT,
    season_number   INTEGER,
    episode_number  INTEGER,
    
    -- File info
    file_path       TEXT NOT NULL,                     -- Relative path from media root
    file_size_bytes BIGINT NOT NULL,
    codec           VARCHAR(20),                       -- 'av1', 'hevc', 'h264'
    resolution      VARCHAR(10),                       -- '4k', '1080p', '720p'
    
    -- Storage state
    storage_tier    VARCHAR(10) NOT NULL DEFAULT 'hot', -- 'hot' (NAS), 'cold' (cloud), 'transferring'
    transfer_direction VARCHAR(10),                     -- 'freezing', 'reheating', NULL
    
    -- Scoring
    temperature     FLOAT NOT NULL DEFAULT 100.0,      -- 0.0 (frozen) to 100.0 (blazing)
    last_scored_at  TIMESTAMPTZ,
    
    -- Jellyfin metadata
    date_added      TIMESTAMPTZ,
    premiere_date   TIMESTAMPTZ,
    community_rating FLOAT,                            -- TMDB/IMDB rating
    
    -- Sonarr/Radarr metadata
    series_status   VARCHAR(20),                       -- 'continuing', 'ended', NULL
    monitored       BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_media_items_jellyfin_id ON media_items(jellyfin_id);
CREATE INDEX idx_media_items_series_id ON media_items(series_id);
CREATE INDEX idx_media_items_temperature ON media_items(temperature);
CREATE INDEX idx_media_items_storage_tier ON media_items(storage_tier);

-- Playback events (append-only log)
CREATE TABLE playback_events (
    id              BIGSERIAL PRIMARY KEY,
    media_item_id   UUID NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
    user_id         VARCHAR(64) NOT NULL,              -- Jellyfin user ID
    username        TEXT,
    event_type      VARCHAR(20) NOT NULL,              -- 'start', 'stop', 'progress'
    play_method     VARCHAR(20),                       -- 'DirectPlay', 'Transcode'
    position_ticks  BIGINT,                            -- Playback position
    duration_ticks  BIGINT,                            -- Total duration
    client_name     TEXT,                              -- 'Jellyfin Web', 'Android', etc.
    device_name     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_playback_events_media_item ON playback_events(media_item_id, created_at DESC);
CREATE INDEX idx_playback_events_created ON playback_events(created_at DESC);

-- Transfer history and active queue
CREATE TABLE transfers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    media_item_id   UUID NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
    direction       VARCHAR(10) NOT NULL,              -- 'freeze' or 'reheat'
    trigger         VARCHAR(20) NOT NULL,              -- 'auto_score', 'prefetch', 'manual', 'space_pressure'
    priority        INTEGER NOT NULL DEFAULT 50,       -- 0-100, higher = more urgent
    
    -- rclone job tracking
    rclone_job_id   INTEGER,                           -- rclone RC async job ID
    rclone_group    VARCHAR(64),                       -- rclone stats group name
    
    -- State
    status          VARCHAR(20) NOT NULL DEFAULT 'queued', -- 'queued', 'active', 'completed', 'failed', 'cancelled'
    
    -- Progress
    bytes_transferred BIGINT DEFAULT 0,
    bytes_total     BIGINT DEFAULT 0,
    speed_bps       BIGINT DEFAULT 0,                  -- bytes per second
    eta_seconds     INTEGER,
    error_message   TEXT,
    
    -- Timestamps
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    
    -- Source/dest for debugging
    source_path     TEXT NOT NULL,
    dest_path       TEXT NOT NULL
);

CREATE INDEX idx_transfers_status ON transfers(status);
CREATE INDEX idx_transfers_media_item ON transfers(media_item_id);

-- Scoring snapshots (for dashboard historical charts)
CREATE TABLE score_history (
    id              BIGSERIAL PRIMARY KEY,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_items     INTEGER NOT NULL,
    hot_items       INTEGER NOT NULL,
    cold_items      INTEGER NOT NULL,
    nas_used_bytes  BIGINT NOT NULL,
    cloud_used_bytes BIGINT NOT NULL,
    avg_temperature FLOAT NOT NULL
);

-- For tracking unique viewers per item (scoring input)
CREATE MATERIALIZED VIEW item_playback_stats AS
SELECT
    pe.media_item_id,
    COUNT(DISTINCT pe.user_id) AS unique_viewers,
    COUNT(*) FILTER (WHERE pe.event_type = 'start') AS total_plays,
    MAX(pe.created_at) FILTER (WHERE pe.event_type = 'start') AS last_played_at,
    COUNT(*) FILTER (
        WHERE pe.event_type = 'start' 
        AND pe.created_at > NOW() - INTERVAL '7 days'
    ) AS plays_last_7d,
    COUNT(*) FILTER (
        WHERE pe.event_type = 'start' 
        AND pe.created_at > NOW() - INTERVAL '30 days'
    ) AS plays_last_30d
FROM playback_events pe
GROUP BY pe.media_item_id;

CREATE UNIQUE INDEX idx_item_playback_stats_id ON item_playback_stats(media_item_id);

-- Refresh this view periodically (every 5 minutes via scheduler)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY item_playback_stats;
```

### 5.4 Temperature Scoring Model

The temperature is a float from 0.0 (frozen solid) to 100.0 (blazing hot). Every media item is scored. The score determines whether Frostbite freezes (moves to cloud) or reheats (moves to NAS) the item.

**Thresholds:**
- `FREEZE_THRESHOLD = 25.0` — Items below this are candidates for freezing
- `REHEAT_THRESHOLD = 60.0` — Items above this that are on cloud should be reheated
- `PREFETCH_BOOST = 40.0` — Flat boost applied to prefetched items

**Scoring formula:**

```python
import math
from datetime import datetime, timedelta

def calculate_temperature(item, stats, config) -> float:
    """
    Calculate temperature score for a media item.
    All weights are configurable via Doppler/ConfigMap.
    """
    now = datetime.utcnow()
    score = 0.0
    
    # ── Factor 1: Recency Decay (0-30 points) ──
    # Exponential decay since last played. Half-life = 14 days.
    if stats.last_played_at:
        days_since = (now - stats.last_played_at).total_seconds() / 86400
        recency = 30.0 * math.exp(-0.0495 * days_since)  # ln(2)/14 ≈ 0.0495
        score += recency
    # Never-played items get 0 recency points
    
    # ── Factor 2: Play Count / Popularity (0-20 points) ──
    # Logarithmic scaling — first few plays matter most
    if stats.total_plays > 0:
        popularity = 20.0 * math.log1p(stats.total_plays) / math.log1p(50)
        score += min(popularity, 20.0)
    
    # ── Factor 3: Unique Viewers (0-15 points) ──
    # More unique viewers = more communal interest = hotter
    if stats.unique_viewers > 0:
        viewer_score = 15.0 * math.log1p(stats.unique_viewers) / math.log1p(20)
        score += min(viewer_score, 15.0)
    
    # ── Factor 4: Trending / Velocity (0-15 points) ──
    # Recent play velocity — plays in last 7 days vs last 30 days
    if stats.plays_last_30d > 0:
        velocity = stats.plays_last_7d / max(stats.plays_last_30d, 1)
        score += 15.0 * min(velocity * 4, 1.0)  # 25%+ of monthly plays in 1 week = max
    
    # ── Factor 5: Newness Boost (0-10 points) ──
    # Recently added items get a grace period before they can be frozen
    if item.date_added:
        days_since_added = (now - item.date_added).total_seconds() / 86400
        if days_since_added < 30:
            newness = 10.0 * (1 - days_since_added / 30)
            score += newness
    
    # ── Factor 6: Series Status (0-5 points) ──
    # Continuing/airing series stay warmer
    if item.series_status == 'continuing':
        score += 5.0
    
    # ── Factor 7: Community Rating Bonus (0-5 points) ──
    # Higher-rated content is more likely to be discovered by new users
    if item.community_rating and item.community_rating > 0:
        score += 5.0 * min(item.community_rating / 10.0, 1.0)
    
    # ── Modifiers ──
    
    # File size pressure: larger files get slight downward pressure
    # This nudges the system to free NAS space by archiving big files first
    size_gb = item.file_size_bytes / (1024**3)
    if size_gb > 5:
        score -= min((size_gb - 5) * 0.5, 5.0)  # Max -5 points for huge files
    
    # Manual override: if user explicitly requested reheat, pin at 100
    # (handled separately in the transfer logic, not in scoring)
    
    return max(0.0, min(100.0, score))
```

**Scoring is event-driven + periodic:**
- **On playback webhook:** Immediately rescore the played item + adjacent episodes
- **On playback stop:** Rescore with completion percentage (did they finish? → hotter)
- **Every 5 minutes:** Refresh `item_playback_stats` materialized view
- **Every 15 minutes:** Full sweep — rescore all items, identify freeze/reheat candidates
- **On NAS space pressure:** Trigger emergency freeze of coldest items

### 5.5 Predictive Prefetch Engine

When a playback event arrives, Frostbite doesn't just score that one item — it predicts what the user will want next.

```python
async def on_playback_start(event: PlaybackEvent):
    """Handle Jellyfin PlaybackStart webhook."""
    item = await get_or_create_media_item(event)
    
    # 1. Record the playback event
    await record_playback_event(event)
    
    # 2. Immediately boost this item's score
    await boost_temperature(item.id, boost=30.0, reason="playback_start")
    
    # 3. Prefetch logic for series
    if item.item_type == 'episode':
        await prefetch_next_episodes(item, count=3)
        await prefetch_season_premiere_if_near_end(item)
    
    # 4. Prefetch logic for movies — warm up "similar" movies
    #    (based on genre overlap in Jellyfin metadata, future enhancement)
    
    # 5. Push live update to dashboard via WebSocket
    await broadcast_score_update(item)

async def prefetch_next_episodes(current: MediaItem, count: int = 3):
    """Queue reheat for next N episodes in the series."""
    next_episodes = await db.execute(
        select(MediaItem)
        .where(
            MediaItem.series_id == current.series_id,
            MediaItem.season_number == current.season_number,
            MediaItem.episode_number > current.episode_number,
            MediaItem.episode_number <= current.episode_number + count
        )
        .order_by(MediaItem.episode_number)
    )
    
    for i, ep in enumerate(next_episodes.scalars()):
        if ep.storage_tier == 'cold':
            priority = 90 - (i * 10)  # First next ep = 90, then 80, 70
            await queue_transfer(
                media_item_id=ep.id,
                direction='reheat',
                trigger='prefetch',
                priority=priority
            )
            # Also boost temperature so it doesn't get re-frozen
            await boost_temperature(ep.id, boost=PREFETCH_BOOST, reason="prefetch")

async def prefetch_season_premiere_if_near_end(current: MediaItem):
    """If within last 2 episodes of season, prefetch next season's premiere."""
    total_in_season = await count_episodes_in_season(
        current.series_id, current.season_number
    )
    if current.episode_number >= total_in_season - 1:
        next_premiere = await get_episode(
            current.series_id, 
            current.season_number + 1, 
            episode_number=1
        )
        if next_premiere and next_premiere.storage_tier == 'cold':
            await queue_transfer(
                media_item_id=next_premiere.id,
                direction='reheat',
                trigger='prefetch',
                priority=75
            )
```

### 5.6 Transfer Manager

Manages the priority queue of freeze/reheat operations. Communicates with the rclone RC daemon on the host VM.

**Design principles:**
- Maximum 2 concurrent transfers (1 freeze + 1 reheat, or 2 reheats). Reheats always take priority.
- Reheat priority order: manual request > active prefetch > auto-score
- Freeze only runs during configurable windows (e.g., 00:00-08:00 IST) OR when NAS free space drops below 20GB
- All transfers are async rclone RC jobs — Frostbite polls `core/stats` every 2 seconds for progress

```python
RCLONE_RC_URL = "http://127.0.0.1:5572"  # Host VM rclone daemon

async def execute_transfer(transfer: Transfer):
    """Execute a freeze or reheat via rclone RC."""
    if transfer.direction == 'freeze':
        # Move from NAS to OpenDrive
        source_fs = f"/mnt/nas/media/"
        dest_fs = "opendrive:media/"
    else:
        # Copy from OpenDrive to NAS (copy, not move — delete cloud copy after verification)
        source_fs = "opendrive:media/"
        dest_fs = f"/mnt/nas/media/"
    
    # Compute relative path
    rel_path = transfer.source_path  # e.g., "tv/Breaking Bad/Season 1/S01E01.mkv"
    
    # Submit async job to rclone RC daemon
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{RCLONE_RC_URL}/sync/copy", json={
            "srcFs": source_fs,
            "dstFs": dest_fs,
            "srcRemote": rel_path,
            "dstRemote": rel_path,
            "_async": True,
            "_group": f"frostbite-{transfer.id}"
        })
        job = resp.json()
        
    # Store job ID for progress tracking
    transfer.rclone_job_id = job.get("jobid")
    transfer.rclone_group = f"frostbite-{transfer.id}"
    transfer.status = "active"
    transfer.started_at = datetime.utcnow()
    await db.commit()

async def poll_transfer_progress(transfer: Transfer) -> dict:
    """Poll rclone RC for transfer progress."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{RCLONE_RC_URL}/core/stats", json={
            "group": transfer.rclone_group
        })
        stats = resp.json()
    
    return {
        "bytes_transferred": stats.get("bytes", 0),
        "bytes_total": stats.get("totalBytes", 0),
        "speed_bps": int(stats.get("speed", 0)),
        "eta_seconds": stats.get("eta"),
        "progress": stats.get("bytes", 0) / max(stats.get("totalBytes", 1), 1)
    }
```

**Post-transfer hooks:**

After a **freeze** completes:
1. Verify file exists on OpenDrive (`rclone lsf opendrive:media/<path>`)
2. Delete the NAS copy (the rclone `sync/move` does this automatically)
3. Invalidate rclone mount cache: `rclone rc vfs/forget dir=<parent_dir>`
4. Update `media_items.storage_tier = 'cold'`
5. Push update to dashboard WebSocket

After a **reheat** completes:
1. Verify file exists on NAS and size matches
2. Optionally delete cloud copy (to save OpenDrive space) OR keep as backup
3. Invalidate rclone mount cache
4. Update `media_items.storage_tier = 'hot'`
5. Push update to dashboard WebSocket

### 5.7 NAS Space Monitor

A background task that watches NAS free space and triggers emergency freezes if needed.

```python
async def check_nas_space():
    """Runs every 5 minutes. Triggers emergency freeze if NAS is filling up."""
    statvfs = os.statvfs("/mnt/nas/media")
    free_bytes = statvfs.f_bavail * statvfs.f_frsize
    free_gb = free_bytes / (1024**3)
    
    if free_gb < EMERGENCY_FREEZE_THRESHOLD_GB:  # e.g., 15GB
        # Find coldest hot items and queue for immediate freeze
        coldest = await db.execute(
            select(MediaItem)
            .where(MediaItem.storage_tier == 'hot')
            .order_by(MediaItem.temperature.asc())
            .limit(10)
        )
        for item in coldest.scalars():
            await queue_transfer(
                media_item_id=item.id,
                direction='freeze',
                trigger='space_pressure',
                priority=95  # Very high priority
            )
```

### 5.8 Jellyfin Webhook Integration

Frostbite receives webhooks from Jellyfin's Webhook plugin.

**Jellyfin Webhook Plugin config:**
- Destination: `http://frostbite-engine:8000/webhook/jellyfin`
- Notification Types: PlaybackStart, PlaybackStop, PlaybackProgress, ItemAdded
- Send All Properties: Yes

```python
@router.post("/webhook/jellyfin")
async def receive_jellyfin_webhook(request: Request):
    payload = await request.json()
    event_type = payload.get("NotificationType")
    
    if event_type == "PlaybackStart":
        await on_playback_start(PlaybackEvent.from_webhook(payload))
    elif event_type == "PlaybackStop":
        await on_playback_stop(PlaybackEvent.from_webhook(payload))
    elif event_type == "PlaybackProgress":
        # Only process every ~30 seconds (ignore intermediate)
        await on_playback_progress(PlaybackEvent.from_webhook(payload))
    elif event_type == "ItemAdded":
        await on_item_added(payload)
    
    return {"ok": True}
```

### 5.9 Initial Library Sync

On first run, Frostbite needs to discover all existing media items and populate the database.

```python
async def initial_sync():
    """Walk the mergerfs mount, discover all media files, create DB records."""
    media_root = "/mnt/merged/media"
    
    for root, dirs, files in os.walk(media_root):
        for f in files:
            if f.endswith(('.mkv', '.mp4', '.avi', '.m4v')):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, media_root)
                
                # Detect tier via mergerfs xattr
                tier = get_storage_tier(full_path)
                
                # Get file size
                size = os.path.getsize(full_path)
                
                # Match to Jellyfin item via path or Jellyfin API search
                jellyfin_item = await jellyfin_client.find_by_path(rel_path)
                
                if jellyfin_item:
                    await upsert_media_item(
                        jellyfin_id=jellyfin_item['Id'],
                        title=jellyfin_item['Name'],
                        item_type=jellyfin_item['Type'].lower(),
                        file_path=rel_path,
                        file_size_bytes=size,
                        storage_tier=tier,
                        # ... more metadata from Jellyfin API
                    )
```

---

## 6. Layer 2B — Frostbite Dashboard (Frontend)

### 6.1 Technology Stack

| Component | Technology |
|---|---|
| Framework | React 18 + TypeScript |
| Build | Vite |
| Styling | TailwindCSS + shadcn/ui |
| Charts | Recharts |
| State | TanStack Query (server state) + Zustand (client state) |
| WebSocket | Native WebSocket with auto-reconnect |
| Routing | React Router v7 |

### 6.2 Dashboard Pages

**1. Overview Dashboard (`/`)**
- Storage utilization donut chart (NAS used / NAS free / Cloud used)
- Temperature distribution histogram (how many items at each temp range)
- Active transfers list with real-time progress bars
- Recent playback activity feed
- NAS free space alert banner (if below threshold)
- Quick stats: total items, hot count, cold count, transfer queue depth

**2. Library Browser (`/library`)**
- Grid/list view of all media items with:
  - Poster image (from Jellyfin)
  - Title, type, resolution
  - Temperature gauge (color-coded: red=hot, blue=cold)
  - Storage tier badge (🔥 Hot / ❄️ Cold / 🔄 Transferring)
  - File size
- Sort by: temperature, name, last played, size, date added
- Filter by: tier (hot/cold/all), type (movie/episode), series
- Click to expand: full scoring breakdown, playback history, transfer history
- Manual actions: "Freeze" button, "Reheat" button, "Pin Hot" toggle

**3. Transfer Queue (`/transfers`)**
- Active transfers with real-time progress (bytes, speed, ETA)
- Queued transfers with priority and trigger reason
- Completed/failed transfer history with timestamps
- Cancel button for active/queued transfers
- Manual "queue freeze all below threshold" button

**4. Heatmap View (`/heatmap`)**
- Visual grid showing all series as rows, episodes as columns
- Each cell colored by temperature (gradient from blue to red)
- Hovering shows tooltip with score breakdown
- Great for seeing binge patterns and prefetch effectiveness

**5. Settings (`/settings`)**
- Scoring weight sliders (recency, popularity, velocity, etc.)
- Threshold configuration (freeze/reheat temperatures)
- Freeze schedule (time windows when freezing is allowed)
- NAS space alerts configuration
- OpenDrive connection status
- Manual triggers: full rescore, initial sync, cache invalidation

### 6.3 WebSocket Protocol

Frostbite pushes real-time updates to the dashboard:

```typescript
// WebSocket message types
type WSMessage =
  | { type: 'score_update'; item_id: string; temperature: number; tier: string }
  | { type: 'transfer_progress'; transfer_id: string; progress: number; speed: number; eta: number }
  | { type: 'transfer_complete'; transfer_id: string; direction: string }
  | { type: 'transfer_failed'; transfer_id: string; error: string }
  | { type: 'playback_event'; item_id: string; username: string; event: string }
  | { type: 'space_alert'; free_gb: number; threshold_gb: number }
  | { type: 'stats_snapshot'; hot: number; cold: number; transferring: number; nas_free_gb: number }
```

### 6.4 Deployment

The dashboard is a static React build served by an nginx container.

```yaml
# frostbite/dashboard-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frostbite-dashboard
  namespace: frostbite
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frostbite-dashboard
  template:
    spec:
      containers:
        - name: dashboard
          image: ghcr.io/pico/frostbite-dashboard:latest  # or local registry
          ports:
            - containerPort: 80
          resources:
            limits:
              memory: 64Mi
              cpu: 100m
```

Ingress at `frostbite.techtronics.top`.

---

## 7. Layer 3 — Jellyfin UI Modifications

### 7.1 Approach

Use the `jellyfin-plugin-custom-javascript` plugin to inject JS into Jellyfin's web UI. This JS communicates with the Frostbite API to:

1. Add cold storage badges to media items
2. Show download progress overlay when playing cold content
3. Add a "Warm Up" button on cold item detail pages

### 7.2 Cold Storage Badge

```javascript
// Injected via Custom JavaScript plugin
(async function frostbiteIntegration() {
    const FROSTBITE_API = 'https://frostbite.techtronics.top/api';
    
    // Hook into Jellyfin's item rendering
    const observer = new MutationObserver(async (mutations) => {
        // Find newly rendered card elements
        const cards = document.querySelectorAll('.card:not([data-frostbite-checked])');
        if (cards.length === 0) return;
        
        // Batch query Frostbite for all visible items
        const itemIds = [...cards].map(c => c.getAttribute('data-id')).filter(Boolean);
        if (itemIds.length === 0) return;
        
        try {
            const resp = await fetch(`${FROSTBITE_API}/status/batch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ item_ids: itemIds })
            });
            const statuses = await resp.json();
            
            for (const card of cards) {
                const id = card.getAttribute('data-id');
                const status = statuses[id];
                card.setAttribute('data-frostbite-checked', 'true');
                
                if (status?.tier === 'cold') {
                    // Add snowflake badge
                    const badge = document.createElement('div');
                    badge.className = 'frostbite-cold-badge';
                    badge.innerHTML = '❄️';
                    badge.title = 'Stored in cloud — may take a moment to start';
                    card.querySelector('.cardImageContainer')?.appendChild(badge);
                }
            }
        } catch (e) {
            console.warn('Frostbite API unavailable', e);
        }
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
})();
```

### 7.3 Playback Progress Overlay

When a user plays a cold file, the rclone VFS cache starts downloading it. Frostbite tracks this via the rclone RC daemon's stats. The injected JS shows a custom loading overlay.

```javascript
// Hook into Jellyfin playback events
document.addEventListener('viewshow', async function() {
    // Detect if we're on the video player page
    const player = document.querySelector('.videoPlayerContainer');
    if (!player) return;
    
    // Get currently playing item ID from Jellyfin's internal state
    const itemId = getCurrentPlayingItemId(); // Extract from Jellyfin's JS API
    if (!itemId) return;
    
    const status = await fetch(`${FROSTBITE_API}/status/${itemId}`).then(r => r.json());
    
    if (status.tier === 'cold' || status.tier === 'transferring') {
        showColdPlaybackOverlay(itemId, status);
    }
});

function showColdPlaybackOverlay(itemId, status) {
    const overlay = document.createElement('div');
    overlay.id = 'frostbite-overlay';
    overlay.innerHTML = `
        <div class="frostbite-loading">
            <div class="frostbite-title">☁️ Streaming from cloud storage</div>
            <div class="frostbite-progress-bar">
                <div class="frostbite-progress-fill" style="width: 0%"></div>
            </div>
            <div class="frostbite-stats">Buffering...</div>
        </div>
    `;
    document.querySelector('.videoPlayerContainer')?.appendChild(overlay);
    
    // Poll Frostbite for VFS cache progress
    const interval = setInterval(async () => {
        const progress = await fetch(`${FROSTBITE_API}/vfs-progress/${itemId}`).then(r => r.json());
        const pct = Math.round(progress.cached_percent * 100);
        overlay.querySelector('.frostbite-progress-fill').style.width = `${pct}%`;
        overlay.querySelector('.frostbite-stats').textContent = 
            `${pct}% cached · ${formatSpeed(progress.speed_bps)} · ETA ${progress.eta_seconds}s`;
        
        // Remove overlay once enough is cached for smooth playback (e.g., 10%)
        if (pct >= 10) {
            overlay.classList.add('frostbite-fade-out');
            setTimeout(() => overlay.remove(), 500);
            clearInterval(interval);
        }
    }, 1000);
}
```

### 7.4 Custom CSS for Badges

Added to Jellyfin's Custom CSS field in Dashboard > General:

```css
/* Frostbite cold storage badge */
.frostbite-cold-badge {
    position: absolute;
    top: 8px;
    right: 8px;
    font-size: 1.4em;
    background: rgba(0, 0, 0, 0.6);
    border-radius: 50%;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    backdrop-filter: blur(4px);
}

/* Frostbite playback overlay */
#frostbite-overlay {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    transition: opacity 0.5s;
}
#frostbite-overlay.frostbite-fade-out { opacity: 0; }
.frostbite-loading { text-align: center; color: white; }
.frostbite-title { font-size: 1.3em; margin-bottom: 16px; }
.frostbite-progress-bar {
    width: 400px; height: 6px;
    background: rgba(255,255,255,0.2);
    border-radius: 3px; overflow: hidden;
}
.frostbite-progress-fill {
    height: 100%; background: #00a4dc;
    border-radius: 3px; transition: width 0.3s;
}
.frostbite-stats { margin-top: 10px; font-size: 0.9em; opacity: 0.8; }
```

### 7.5 "Warm Up" Button on Item Detail Pages

Injected on item detail pages for cold content:

```javascript
// On item detail page load
async function addWarmUpButton() {
    const itemId = getItemIdFromPage();
    if (!itemId) return;
    
    const status = await fetch(`${FROSTBITE_API}/status/${itemId}`).then(r => r.json());
    if (status.tier !== 'cold') return;
    
    const detailSection = document.querySelector('.detailPageContent .itemDetailPage');
    if (!detailSection) return;
    
    const btn = document.createElement('button');
    btn.className = 'button-submit frostbite-warmup-btn';
    btn.innerHTML = '🔥 Warm Up for Playback';
    btn.onclick = async () => {
        btn.disabled = true;
        btn.innerHTML = '⏳ Warming up...';
        await fetch(`${FROSTBITE_API}/reheat/${itemId}`, { method: 'POST' });
        
        // Poll until reheated
        const poll = setInterval(async () => {
            const s = await fetch(`${FROSTBITE_API}/status/${itemId}`).then(r => r.json());
            if (s.tier === 'hot') {
                btn.innerHTML = '✅ Ready to play!';
                btn.className = 'button-submit frostbite-warmup-btn frostbite-ready';
                clearInterval(poll);
            } else if (s.tier === 'transferring') {
                const pct = Math.round((s.bytes_transferred / s.bytes_total) * 100);
                btn.innerHTML = `⏳ Warming up... ${pct}%`;
            }
        }, 2000);
    };
    
    detailSection.insertBefore(btn, detailSection.firstChild);
}
```

---

## 8. Kubernetes Manifests Overview

### 8.1 Namespace and Secrets

```yaml
# frostbite/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: frostbite

# frostbite/doppler-secret.yaml
apiVersion: secrets.doppler.com/v1alpha1
kind: DopplerSecret
metadata:
  name: frostbite-doppler
  namespace: doppler-operator-system
spec:
  tokenSecret:
    name: doppler-token-secret
  managedSecret:
    name: frostbite-secrets
    namespace: frostbite
  config: main
  project: rke2-cluster    # or a dedicated 'frostbite' project in Doppler
```

**Doppler secrets needed:**
- `OPENDRIVE_USER` / `OPENDRIVE_PASS` — for rclone config (used on VM, not in K8s)
- `JELLYFIN_API_KEY` — for Frostbite to query Jellyfin API
- `SONARR_API_KEY` / `RADARR_API_KEY` — for series/movie metadata
- `POSTGRES_PASSWORD` — for the Frostbite database
- `FROSTBITE_SECRET_KEY` — for API auth between Jellyfin JS and Frostbite API

### 8.2 PostgreSQL

```yaml
# frostbite/postgresql.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: frostbite-db
  namespace: frostbite
spec:
  serviceName: frostbite-db
  replicas: 1
  selector:
    matchLabels:
      app: frostbite-db
  template:
    metadata:
      labels:
        app: frostbite-db
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: frostbite
            - name: POSTGRES_USER
              value: frostbite
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: frostbite-secrets
                  key: POSTGRES_PASSWORD
          volumeMounts:
            - name: pgdata
              mountPath: /var/lib/postgresql/data
          resources:
            requests:
              memory: 256Mi
              cpu: 200m
            limits:
              memory: 512Mi
              cpu: 500m
  volumeClaimTemplates:
    - metadata:
        name: pgdata
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: longhorn
        resources:
          requests:
            storage: 5Gi
```

### 8.3 Frostbite Engine

```yaml
# frostbite/engine-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frostbite-engine
  namespace: frostbite
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frostbite-engine
  template:
    metadata:
      labels:
        app: frostbite-engine
    spec:
      hostNetwork: true          # Access rclone RC daemon on 127.0.0.1:5572
      dnsPolicy: ClusterFirstWithHostNet
      containers:
        - name: engine
          image: ghcr.io/pico/frostbite-engine:latest
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              value: "postgresql+asyncpg://frostbite:$(POSTGRES_PASSWORD)@frostbite-db.frostbite:5432/frostbite"
            - name: RCLONE_RC_URL
              value: "http://127.0.0.1:5572"
            - name: MEDIA_ROOT
              value: "/media"
            - name: NAS_ROOT
              value: "/mnt/nas/media"
            - name: CLOUD_ROOT
              value: "/mnt/cloud/media"
          envFrom:
            - secretRef:
                name: frostbite-secrets
          volumeMounts:
            - name: media
              mountPath: /media
              readOnly: true      # Engine reads via mergerfs (for xattr queries)
            - name: nas-direct
              mountPath: /mnt/nas/media
              readOnly: true      # Direct NAS access for size checks
          resources:
            requests:
              memory: 256Mi
              cpu: 200m
            limits:
              memory: 512Mi
              cpu: 1000m
      volumes:
        - name: media
          hostPath:
            path: /mnt/merged/media
            type: Directory
        - name: nas-direct
          hostPath:
            path: /mnt/nas/media
            type: Directory
```

### 8.4 Services and Ingress

```yaml
# frostbite/services.yaml
apiVersion: v1
kind: Service
metadata:
  name: frostbite-engine
  namespace: frostbite
spec:
  # Note: With hostNetwork, this service routes to the pod's host port
  selector:
    app: frostbite-engine
  ports:
    - port: 8000
      targetPort: 8000
      name: api
---
apiVersion: v1
kind: Service
metadata:
  name: frostbite-db
  namespace: frostbite
spec:
  clusterIP: None
  selector:
    app: frostbite-db
  ports:
    - port: 5432
---
apiVersion: v1
kind: Service
metadata:
  name: frostbite-dashboard
  namespace: frostbite
spec:
  selector:
    app: frostbite-dashboard
  ports:
    - port: 80
      targetPort: 80

# frostbite/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: frostbite-ingress
  namespace: frostbite
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"      # WebSocket support
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    nginx.ingress.kubernetes.io/upstream-hash-by: "$remote_addr" # Sticky for WS
spec:
  ingressClassName: nginx
  rules:
    - host: frostbite.techtronics.top
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: frostbite-engine
                port:
                  number: 8000
          - path: /ws
            pathType: Prefix
            backend:
              service:
                name: frostbite-engine
                port:
                  number: 8000
          - path: /webhook
            pathType: Prefix
            backend:
              service:
                name: frostbite-engine
                port:
                  number: 8000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frostbite-dashboard
                port:
                  number: 80
```

### 8.5 Git Repository Structure

```
kubernetes/frostbite/
├── namespace.yaml
├── doppler-secret.yaml
├── postgresql.yaml
├── engine-deployment.yaml
├── dashboard-deployment.yaml
├── services.yaml
├── ingress.yaml
└── configmap.yaml          # Scoring weights, thresholds, schedule
```

All managed via ArgoCD.

---

## 9. API Specification (Key Endpoints)

### Frostbite Engine REST API

| Method | Path | Purpose |
|---|---|---|
| POST | `/webhook/jellyfin` | Receive Jellyfin webhook events |
| GET | `/api/status/{jellyfin_item_id}` | Get item storage tier, temperature, transfer status |
| POST | `/api/status/batch` | Batch query status for multiple items (for Jellyfin UI) |
| GET | `/api/items` | List all items with filtering/sorting/pagination |
| GET | `/api/items/{id}/history` | Get playback and transfer history for an item |
| POST | `/api/reheat/{jellyfin_item_id}` | Manually queue a reheat for an item |
| POST | `/api/freeze/{jellyfin_item_id}` | Manually queue a freeze for an item |
| POST | `/api/pin/{jellyfin_item_id}` | Pin item as permanently hot (never freeze) |
| DELETE | `/api/pin/{jellyfin_item_id}` | Unpin item |
| GET | `/api/transfers` | List active and queued transfers |
| DELETE | `/api/transfers/{id}` | Cancel a transfer |
| GET | `/api/vfs-progress/{jellyfin_item_id}` | Get rclone VFS cache progress for a playing cold file |
| GET | `/api/dashboard` | Aggregate stats for dashboard overview |
| GET | `/api/heatmap/{series_id}` | Get temperature grid for a series (for heatmap view) |
| GET | `/api/settings` | Get current scoring config |
| PUT | `/api/settings` | Update scoring config |
| POST | `/api/sync` | Trigger initial library sync |
| POST | `/api/rescore` | Trigger full rescore |
| WS | `/ws` | WebSocket for live dashboard updates |

### Authentication

The Frostbite API uses a shared secret (`FROSTBITE_SECRET_KEY`) passed as a Bearer token. The Jellyfin custom JS includes this token in its requests. The dashboard uses the same token. For a semi-public Jellyfin instance, this is sufficient — the token is embedded in the custom JS served to authenticated Jellyfin users only.

For the webhook endpoint, Jellyfin's webhook plugin can include a custom header. Frostbite validates `X-Frostbite-Key` on incoming webhooks.

---

## 10. Operational Considerations

### 10.1 Failure Modes

| Failure | Impact | Mitigation |
|---|---|---|
| **OpenDrive down** | Cold files inaccessible, rclone mount returns errors | mergerfs still serves hot files. Jellyfin shows errors only for cold content. Frostbite dashboard shows alert. |
| **rclone mount crashes** | mergerfs loses cloud branch, cold files disappear from library | systemd auto-restarts. mergerfs can be configured with `branches-mount-timeout` to wait. Jellyfin library scan will remove cold items temporarily; they reappear after rclone restarts. |
| **mergerfs crashes** | All media access lost | systemd auto-restarts. All pods reading from hostPath will get I/O errors until mergerfs recovers. Consider liveness probes. |
| **Frostbite engine crashes** | No scoring, no prefetching, no transfers | Existing hot/cold distribution stays put. No data loss. Jellyfin still works. Manual transfers stop. systemd/K8s restarts pod. |
| **NAS full** | Sonarr/Radarr can't import new downloads | Frostbite's space monitor triggers emergency freeze. `moveonenospc=true` in mergerfs sends overflow writes to cloud. |
| **PostgreSQL down** | Frostbite engine can't score or track | Engine enters degraded mode — still serves status from in-memory cache, stops new scoring. PG restarts via StatefulSet. |
| **Mid-transfer crash** | Partial file on destination | rclone handles resume on next attempt. Frostbite marks transfer as `failed` after timeout, retries automatically. |
| **OpenDrive throttling** | Uploads very slow (past 10TB) | Frostbite respects this — freeze transfers run at throttled speed. Dashboard shows actual speed. Reheats (downloads) are unthrottled. |

### 10.2 Monitoring

- **rclone mount health:** Periodic `stat /mnt/cloud/media` check from VM
- **mergerfs health:** Periodic `stat /mnt/merged/media/.mergerfs` check
- **NAS space:** Frostbite monitors via `os.statvfs()`, pushes to dashboard
- **Transfer throughput:** Logged in PG, graphed in dashboard
- **OpenDrive API latency:** Measured from rclone mount `--log-level INFO`
- **Scoring distribution:** Historical snapshots in `score_history` table, graphed in dashboard

### 10.3 Backup Strategy

- **PostgreSQL:** Longhorn snapshots (automated via Longhorn recurring jobs)
- **Scoring config:** In Git (ConfigMap), synced by ArgoCD
- **Media files:** NAS is the primary copy. OpenDrive is the cold tier (secondary). For truly critical content, both copies exist during the grace period between freeze and cloud-copy-deletion.
- **rclone config:** Managed via Doppler secrets, reproducible

### 10.4 Performance Estimates

| Operation | Expected Performance |
|---|---|
| Jellyfin library scan (5000 items, mixed hot/cold) | ~10-30s (mergerfs dir cache + rclone dir cache) |
| Cold file playback start (500MB AV1 episode) | ~2-3s to begin (64MB chunk at 37 MB/s) |
| Cold file playback start (2GB AV1 movie) | ~2-3s to begin (same chunk logic) |
| Full episode reheat (500MB) | ~14s |
| Full movie reheat (2GB) | ~57s |
| Freeze upload (500MB, throttled above 10TB) | Variable, potentially minutes-hours depending on OpenDrive throttle |
| Batch status query (100 items) | ~5ms (PostgreSQL indexed query) |
| Temperature calculation (single item) | ~1ms (in-memory math) |
| Full library rescore (5000 items) | ~5-10s |

---

## 11. Implementation Phases

### Phase 1: Storage Infrastructure (Week 1)
- [ ] Install mergerfs on Ubuntu 24.04 VM
- [ ] Configure rclone OpenDrive remote (`rclone config`)
- [ ] Set up `rclone-mount.service`, `rclone-rcd.service`, `mergerfs-media.service`
- [ ] Test: verify `/mnt/merged/media` shows files from both NAS and a test cloud directory
- [ ] Test: verify `getfattr -n user.mergerfs.basepath` returns correct branch
- [ ] Migrate Jellyfin/Sonarr/Radarr manifests from SMB CSI to hostPath (`/mnt/merged/media`)
- [ ] Verify all apps still work with the new mount
- [ ] Manually `rclone copy` a few files to OpenDrive to test cloud reads via mergerfs

### Phase 2: Frostbite Engine MVP (Week 2-3)
- [ ] Deploy PostgreSQL StatefulSet
- [ ] Build Frostbite FastAPI app skeleton (Dockerfile, basic routes)
- [ ] Implement initial library sync (walk mergerfs, populate `media_items`)
- [ ] Implement Jellyfin webhook receiver (playback start/stop → `playback_events`)
- [ ] Implement basic scoring (recency + play count only)
- [ ] Implement transfer manager (freeze/reheat via rclone RC)
- [ ] Test: manually trigger freeze/reheat via API, verify files move correctly
- [ ] Test: verify mergerfs xattr detection works after transfer

### Phase 3: Live Scoring + Prefetch (Week 3-4)
- [ ] Implement full scoring model with all 7 factors
- [ ] Implement materialized view refresh scheduler
- [ ] Implement prefetch engine (next 3 episodes, season premiere)
- [ ] Implement NAS space monitor + emergency freeze
- [ ] Implement WebSocket for live updates
- [ ] Test: play an episode, verify next 3 queue for reheat
- [ ] Test: NAS space pressure triggers freeze

### Phase 4: Frostbite Dashboard (Week 4-5)
- [ ] Scaffold React + Vite + TailwindCSS + shadcn/ui
- [ ] Build Overview page (stats, active transfers, recent activity)
- [ ] Build Library Browser with temperature gauges
- [ ] Build Transfer Queue page with real-time progress
- [ ] Build Heatmap view for series
- [ ] Wire up WebSocket for live updates
- [ ] Deploy as nginx container with Ingress

### Phase 5: Jellyfin UI Mods (Week 5-6)
- [ ] Install `jellyfin-plugin-custom-javascript`
- [ ] Implement cold storage badges (❄️ on cards)
- [ ] Implement "Warm Up" button on item detail pages
- [ ] Implement playback progress overlay for cold content
- [ ] Add Custom CSS for all Frostbite UI elements
- [ ] Test with multiple users, different clients (web, Android, TV)

### Phase 6: Tuning + Polish (Ongoing)
- [ ] Tune scoring weights based on real usage data
- [ ] Add Sonarr/Radarr API integration for series status scoring
- [ ] Add genre-based "similar movie" prefetching
- [ ] Build settings page for dashboard
- [ ] Add score history charts
- [ ] Optimize mergerfs cache settings based on observed patterns
- [ ] Document everything in project wiki

---

## 12. Open Questions & Future Ideas

1. **OpenDrive reliability:** Reviews suggest data integrity issues. Should Frostbite maintain a manifest of cloud files (checksums) and verify periodically? Cost: more API calls. Benefit: catch silent corruption.

2. **Multi-cloud support:** If OpenDrive becomes unusable, could Frostbite support swapping to Backblaze B2 or Cloudflare R2? The rclone abstraction makes this relatively easy — just change the remote name.

3. **Smart Tdarr integration:** When a file is reheated and it hasn't been AV1-encoded yet (e.g., it was frozen before Tdarr got to it), should Frostbite notify Tdarr to encode it before re-freezing?

4. **Jellyfin SSO for Frostbite dashboard:** Currently uses a shared API key. Could integrate with Jellyfin's auth to allow admin-only access to the dashboard.

5. **Mobile app clients:** The custom JS only works in Jellyfin's web client. Android/iOS/TV apps won't show cold badges or warm-up buttons. Solutions: custom Jellyfin plugin (server-side), or accept that non-web clients just get slightly slower cold playback starts.

6. **rclone mount vs rclone serve:** Instead of FUSE mounting, rclone can serve files via WebDAV/HTTP. Jellyfin could access cloud files via HTTP. This avoids FUSE entirely but requires different mergerfs-like logic at the app layer.

7. **Cost tracking:** Dashboard could show estimated OpenDrive cost savings vs. buying more NAS storage. At $10/mo for "unlimited" vs. $15-20/TB for HDDs, the breakeven is ~6 months per TB offloaded.

---

*Document version: 1.0*  
*Author: PICO + Claude*  
*Last updated: March 2026*  
*Project: Teapot (Jellyfin) / Frostbite (Tiered Storage Engine)*
