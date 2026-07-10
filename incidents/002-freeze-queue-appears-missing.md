# Freeze Queue Appears Missing

## Date

2026-07-11

## Symptoms

- NAS usage was above the configured `3072 GiB` cold-transfer start limit, but no freezes were active or queued.
- The cold-transfer gate and Upcoming Freezes sections were absent from the Overview page.
- Repeated scoring sweeps reported `+0 freeze` despite cold items remaining on the NAS.

## Affected

- Automatic freeze scheduling
- Overview operational visibility
- Hot media with filenames longer than OpenDrive's safe limit

## Root Cause

The NAS usage gate was open and operating correctly. The live database contained 229 hot, Tdarr-eligible items below the `10.0` freeze temperature threshold, but every candidate had `upload_blocked=true`. Their filenames ranged from 121 to 247 characters; Frostbite intentionally refuses these uploads because OpenDrive can silently drop filenames above approximately 120 characters.

The dashboard only rendered the cold-transfer notice when the gate was paused or freezes were queued. It also rendered Upcoming Freezes only when `queued_freeze_list` was non-empty. With every candidate blocked before queue creation, both sections disappeared and concealed the actual blocker.

## Fix Steps

1. Kept the OpenDrive filename safety gate in place.
2. Made the cold-transfer gate status visible even when open and idle.
3. Made Upcoming Freezes persistent with an empty-state explanation.
4. Added dashboard counts for below-threshold freeze candidates and candidates blocked by filename length.

The affected files still need to be renamed to 120 characters or fewer through the media-management naming workflow before Frostbite can freeze them safely.

## Prevention

- Keep transfer-gate and queue-status panels visible in idle and blocked states.
- Surface aggregate pre-queue blocker counts instead of representing only persisted transfer rows.
- Preserve the filename-length guard unless OpenDrive's behavior is verified to support longer names safely.
