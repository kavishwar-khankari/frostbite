# CLAUDE.md

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
