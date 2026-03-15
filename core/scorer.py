"""Temperature scoring engine.

Score = float in [0.0, 100.0].
Items below FREEZE_THRESHOLD are freeze candidates.
Items above REHEAT_THRESHOLD that are cold should be reheated.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from config import settings


@dataclass
class PlaybackStats:
    last_played_at: datetime | None
    total_plays: int
    unique_viewers: int
    plays_last_7d: int
    plays_last_30d: int


@dataclass
class ItemMeta:
    file_size_bytes: int
    date_added: datetime | None
    series_status: str | None  # 'continuing', 'ended', None
    community_rating: float | None


def _naive_utc(dt: datetime) -> datetime:
    """Strip timezone info, converting to UTC first if aware."""
    if dt.tzinfo is not None:
        from datetime import timezone
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def calculate_temperature(item: ItemMeta, stats: PlaybackStats) -> float:
    """Calculate temperature score for a media item."""
    now = datetime.utcnow()
    score = 0.0

    # ── Factor 1: Recency Decay (0-30 points) ──
    # Exponential decay since last played. Half-life = 14 days.
    if stats.last_played_at:
        days_since = (now - _naive_utc(stats.last_played_at)).total_seconds() / 86400
        score += 30.0 * math.exp(-0.0495 * days_since)  # ln(2)/14 ≈ 0.0495

    # ── Factor 2: Play Count / Popularity (0-20 points) ──
    if stats.total_plays > 0:
        score += min(20.0 * math.log1p(stats.total_plays) / math.log1p(50), 20.0)

    # ── Factor 3: Unique Viewers (0-15 points) ──
    if stats.unique_viewers > 0:
        score += min(15.0 * math.log1p(stats.unique_viewers) / math.log1p(20), 15.0)

    # ── Factor 4: Trending / Velocity (0-15 points) ──
    if stats.plays_last_30d > 0:
        velocity = stats.plays_last_7d / max(stats.plays_last_30d, 1)
        score += 15.0 * min(velocity * 4, 1.0)

    # ── Factor 5: Newness Boost (0-10 points) ──
    if item.date_added:
        days_since_added = (now - _naive_utc(item.date_added)).total_seconds() / 86400
        if days_since_added < 30:
            score += 10.0 * (1 - days_since_added / 30)

    # ── Factor 6: Series Status (0-5 points) ──
    if item.series_status == "continuing":
        score += 5.0

    # ── Factor 7: Community Rating Bonus (0-5 points) ──
    if item.community_rating and item.community_rating > 0:
        score += 5.0 * min(item.community_rating / 10.0, 1.0)

    # ── Modifier: File size pressure ──
    size_gb = item.file_size_bytes / (1024 ** 3)
    if size_gb > 5:
        score -= min((size_gb - 5) * 0.5, 5.0)

    return max(0.0, min(100.0, score))
