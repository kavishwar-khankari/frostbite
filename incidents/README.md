# Incidents

Quick-reference tracker for Frostbite-specific operational incidents. Each incident has a dedicated file in this directory.

For cluster-wide or infrastructure incidents (e.g. Longhorn, networking, node failures), see the [kubernetes-homelab incidents directory](../kubernetes-homelab/incidents/).

## Index

| # | Date | Title | Severity | Affected Component(s) | Root Cause | Status |
|---|------|-------|----------|-----------------------|------------|--------|
| 001 | 2026-06-09 | [Supernatural Jellyfin mount disconnect](001-supernatural-jellyfin-mount-disconnect.md) | Sev2 | Jellyfin playback, hostPath, mergerfs | Unattended host maintenance restarted node 3 mergerfs while Jellyfin pod kept stale FUSE bind mount | RCA complete, recovery pending pod restart |
