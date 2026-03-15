"""mergerfs xattr helpers and file discovery."""

import os
import subprocess
from pathlib import Path

from config import settings


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
    try:
        sv = os.statvfs(settings.nas_root)
        return sv.f_bavail * sv.f_frsize
    except OSError:
        return 0
