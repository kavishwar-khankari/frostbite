# 001 - Supernatural Jellyfin mount disconnect

## Date

2026-06-09

## Symptoms

- A friend reported that Supernatural suddenly stopped playing in Jellyfin.
- Refreshing Supernatural Season 2 in Jellyfin failed with `System.IO.IOException: Transport endpoint is not connected` for `/media_2/series/web series/Supernatural/Season 2`.
- A pod-level check showed even `/media_2` returned `Transport endpoint is not connected` inside the Jellyfin container.
- The node 3 host mount was healthy at the time of investigation: `/mnt/merged/media` and `/mnt/cloud/media` both existed and `mergerfs-media.service`, `rclone-mount.service`, and `rclone-rcd.service` were active.

## Affected

- Jellyfin playback for all media paths served through `/media_2` while the pod was running on node 3.
- The Jellyfin pod `jellyfin-5f4858cb45-rgcfm`, scheduled on `k3s-node-3`.

## Root Cause

The node 3 host `mergerfs-media.service` was restarted by host maintenance while the Jellyfin pod was already running.

Evidence:

- Jellyfin pod start time: `2026-06-08T12:07:27Z`.
- Node 3 `mergerfs-media.service` restarted at `2026-06-09T06:21:08Z`.
- Node logs around the restart show `apt-daily-upgrade.service` / unattended-upgrade activity and service restarts.
- Apt history shows unattended upgrades from `2026-06-09 06:20:57` to `06:21:17`, including `systemd`, `udev`, `libsystemd0`, `libudev1`, `systemd-resolved`, `systemd-timesyncd`, `rsync`, and related packages.
- After the host remounted mergerfs, the host saw the new healthy `/mnt/merged/media` mount, but the already-running Jellyfin pod kept a bind mount to the old dead FUSE superblock.
- The Jellyfin deployment already had `mountPropagation: HostToContainer` for `/media_2`, but node 3 reported `PROPAGATION=private` for `/`, `/mnt/merged/media`, and `/mnt/cloud/media`. Because the host mount tree is private, mount events are not propagated into the running pod as intended.

This presents in containers as `Transport endpoint is not connected`. Restarting the host FUSE service alone is insufficient because Kubernetes does not automatically rebind hostPath mounts inside already-running pods.

A secondary, unrelated consistency gap was found while investigating: Frostbite's freeze fast path for files that already existed on cloud deleted the NAS copy and returned without refreshing all rclone VFS caches. That gap can cause stale directory visibility, but it does not explain Jellyfin's `Transport endpoint is not connected` error for `/media_2` itself.

## Fix Steps

Immediate recovery:

```bash
kubectl delete pod -n jellyfin jellyfin-5f4858cb45-rgcfm
```

Deleting the pod lets the Deployment recreate it and bind `/media_2` to the current healthy host mount.

Validation after recovery:

```bash
kubectl exec -n jellyfin deploy/jellyfin -c jellyfin -- sh -c 'ls -ld /media_2 "/media_2/series/web series/Supernatural/Season 2"'
```

Code cleanup completed during investigation:

- Fixed `core/transfer_manager.py` so the freeze fast path now refreshes VFS cache after deleting the NAS copy.
- Refactored the VFS refresh into `_refresh_vfs_cache()` and reused it from both normal transfer completion and the already-on-cloud shortcut.
- `_refresh_vfs_cache()` now calls `vfs/forget` for the file before refreshing the parent directory on every configured `settings.rclone_vfs_urls` endpoint.

Operational checks used for this incident:

```bash
kubectl get pods -A -o wide
kubectl exec -n jellyfin jellyfin-5f4858cb45-rgcfm -c jellyfin -- sh -c 'ls -ld /media_2'

# On the affected node host:
stat /mnt/merged/media
stat /mnt/cloud/media
systemctl is-active mergerfs-media.service
systemctl is-active rclone-mount.service
systemctl is-active rclone-rcd.service
journalctl -u mergerfs-media.service -u rclone-mount.service --since "2 hours ago" --no-pager -n 120

# For item-level checks after the mount itself is healthy:
cd "/mnt/merged/media/series/web series" && test -d "Supernatural" && echo present
getfattr -n user.mergerfs.basepath --only-values "/mnt/merged/media/series/web series/Supernatural/Season 2/Supernatural - S02E01 - In My Time of Dying Bluray-1080p.mkv"
```

## Prevention

- Do not restart `mergerfs-media.service` or `rclone-mount.service` on a node with live hostPath consumers without restarting those pods afterwards.
- If relying on mount propagation, configure the host mount tree as shared/rshared before pods start. `mountPropagation: HostToContainer` on the pod is not enough when the host source mount is private.
- Disable or constrain unattended upgrades on Kubernetes media nodes so package maintenance cannot restart host FUSE services during active Jellyfin playback. At minimum, prevent unattended `systemd`/`udev` upgrades outside a controlled maintenance window.
- Add a node-level hook for `mergerfs-media.service` and `rclone-mount.service` restarts that cordons/drains the node or restarts affected pods after the mount is healthy.
- Add a Jellyfin liveness/readiness check that fails if `stat /media_2` returns `Transport endpoint is not connected`.
- Add a recurring health check that compares `/mnt/merged/media` on the host and `/media_2` inside the Jellyfin pod.
- Every successful Frostbite path that removes or adds a cloud-visible media file must call the shared VFS refresh helper.
