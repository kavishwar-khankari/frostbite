# 003 - Shin Chan cold-tier VFS cache hid episodes

## Date

2026-07-30

## Symptoms

- Jellyfin displayed only 7 of 138 Shin Chan episodes after Frostbite froze 131 episodes.
- The NAS library path contained only the seven hot files.
- Frostbite recorded all 131 freeze transfers as complete, but `/mnt/cloud/media/series/anime/Shin Chan (1992)` initially appeared absent on node 3.

## Affected

- Jellyfin playback and browsing for `Shin Chan (1992)`.
- rclone VFS cache and mergerfs on all media nodes.

## Root Cause

Frostbite successfully copied each episode to the encrypted OpenDrive remote, verified its size, then deleted the NAS copy as designed. The rclone VFS mount retained a negative cache entry for the series directory. Frostbite invalidated only the individual file entry after each transfer, so the 72-hour `--dir-cache-time` could continue to hide the newly-created cloud series directory from mergerfs and Jellyfin.

The cloud objects were verified through rclone RC: all eight Shin Chan season directories existed at `series/anime/Shin Chan (1992)`.

## Fix Steps

1. Added a Frostbite deletion exception for the current Shin Chan series record.
2. Issued `vfs/forget` for `series/anime/Shin Chan (1992)` on all rclone mounts.
3. Confirmed Jellyfin's mount could again see the cloud-backed episodes and `ffprobe` could read an offloaded episode.
4. Updated Frostbite invalidation to forget the file, season directory, and series directory after storage changes.

## Prevention

- Forget parent and series directory cache entries along with each changed file.
- Keep the existing VFS refresh requests as a secondary cache-warming mechanism.
- Add regression coverage for both transfer and deletion invalidation paths.
- Preserve media through Frostbite exceptions before investigating availability incidents.
