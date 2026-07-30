# Incidents

Quick-reference tracker for Frostbite-specific operational incidents. Each incident has a dedicated file in this directory.

For cluster-wide or infrastructure incidents (e.g. Longhorn, networking, node failures), see the [kubernetes-homelab incidents directory](../kubernetes-homelab/incidents/).

## Index

| # | Date | Title | Severity | Affected Component(s) | Root Cause | Status |
|---|------|-------|----------|-----------------------|------------|--------|
| 001 | 2026-06-09 | [Supernatural Jellyfin mount disconnect](001-supernatural-jellyfin-mount-disconnect.md) | Sev2 | Jellyfin playback, hostPath, mergerfs | Unattended host maintenance restarted node 3 mergerfs while Jellyfin pod kept stale FUSE bind mount | RCA complete, recovery pending pod restart |
| 002 | 2026-07-11 | [Freeze queue appears missing](002-freeze-queue-appears-missing.md) | Sev3 | Freeze scheduler, dashboard | All below-threshold hot candidates exceeded OpenDrive's safe filename length while the dashboard hid empty operational panels | Fixed locally, deployment pending |
| 003 | 2026-07-30 | [Shin Chan cold-tier VFS cache hid episodes](003-shin-chan-cold-tier-vfs-cache.md) | Sev2 | Frostbite transfer manager, rclone VFS, Jellyfin | File-only VFS invalidation left a negative series-directory cache entry after offload | Fixed locally, deployment pending |
