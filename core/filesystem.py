"""mergerfs xattr helpers and file discovery."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from config import settings


BYTES_PER_GIB = 1024 ** 3
BYTES_PER_GB = 1_000_000_000


@dataclass(frozen=True)
class StorageUsage:
    total_bytes: int
    available_bytes: int
    used_bytes: int


def bytes_to_gib(value: int | None) -> float | None:
    return None if value is None else value / BYTES_PER_GIB


def gib_to_bytes(value: float) -> int:
    return int(value * BYTES_PER_GIB)


def stat_storage(root: str = settings.nas_root) -> StorageUsage | None:
    """Return raw storage stats for a mount, or None if statvfs fails."""
    try:
        sv = os.statvfs(root)
    except OSError:
        return None

    total = sv.f_blocks * sv.f_frsize
    available = sv.f_bavail * sv.f_frsize
    return StorageUsage(
        total_bytes=total,
        available_bytes=available,
        used_bytes=max(total - available, 0),
    )


def get_storage_tier(full_path: str) -> str:
    """Detect whether a file lives on NAS or cloud via mergerfs xattr."""
    try:
        result = subprocess.run(
            ["getfattr", "-n", "user.mergerfs.basepath", "--only-values", full_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            basepath = result.stdout.strip()
            if basepath.startswith(settings.nas_root):
                return "hot"
            return "cold"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: check if the file exists on NAS directly
    rel = os.path.relpath(full_path, settings.media_root)
    nas_path = os.path.join(settings.nas_root, rel)
    return "hot" if os.path.exists(nas_path) else "cold"


def iter_media_files(root: str = settings.media_root):
    """Yield (full_path, rel_path, size_bytes) for all media files under root."""
    extensions = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv"}
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            if Path(fname).suffix.lower() in extensions:
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, root)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                yield full, rel, size


def nas_free_bytes() -> int:
    """Return free bytes on the NAS mount."""
    usage = stat_storage(settings.nas_root)
    return usage.available_bytes if usage else 0


def nas_used_bytes() -> int | None:
    """Return bytes used on the NAS mount, or None if statvfs fails."""
    usage = stat_storage(settings.nas_root)
    return usage.used_bytes if usage else None
