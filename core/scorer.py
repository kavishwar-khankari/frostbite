"""Temperature scoring engine.

Score = float in [0.0, 100.0].
Items below FREEZE_THRESHOLD are freeze candidates.
Items above REHEAT_THRESHOLD that are cold should be reheated.

Only items marked tdarr_eligible=True are scored by the sweep;
everything else stays at its default temperature (100 = always hot).
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


def calculate_temperature_with_breakdown(
    item: ItemMeta, stats: PlaybackStats
) -> tuple[float, dict]:
    """
    Calculate temperature score with a per-factor breakdown.
    Returns (score, breakdown_dict).

    Factor weights (max points):
      1. Recency decay        — 30 pts  (exponential decay since last play)
      2. Play count           — 20 pts  (log scale up to 50 plays)
      3. Unique viewers       — 15 pts  (log scale up to 20 viewers)
      4. Trending velocity    — 15 pts  (7d plays / 30d plays ratio)
      5. Newness boost        — 30 pts  (full for 7 days, linear decay to 0 at 30 days)
      6. Series status        —  5 pts  (continuing series)
      7. Community rating     —  5 pts  (0–10 scale)
      8. Size penalty         —  -5 pts (files > 5 GB)
    """
    now = datetime.utcnow()
    b: dict[str, float] = {}

    # ── Factor 1: Recency Decay (0–30 pts) ────────────────────────────────────
    # Half-life = 14 days: score halves every 14 days since last play.
    f1 = 0.0
    if stats.last_played_at:
        days = (now - _naive_utc(stats.last_played_at)).total_seconds() / 86400
        f1 = 30.0 * math.exp(-0.0495 * days)  # ln(2)/14 ≈ 0.0495
    b["recency"] = round(f1, 1)

    # ── Factor 2: Play Count (0–20 pts) ───────────────────────────────────────
    f2 = 0.0
    if stats.total_plays > 0:
        f2 = min(20.0 * math.log1p(stats.total_plays) / math.log1p(50), 20.0)
    b["play_count"] = round(f2, 1)

    # ── Factor 3: Unique Viewers (0–15 pts) ───────────────────────────────────
    f3 = 0.0
    if stats.unique_viewers > 0:
        f3 = min(15.0 * math.log1p(stats.unique_viewers) / math.log1p(20), 15.0)
    b["unique_viewers"] = round(f3, 1)

    # ── Factor 4: Trending / Velocity (0–15 pts) ──────────────────────────────
    f4 = 0.0
    if stats.plays_last_30d > 0:
        velocity = stats.plays_last_7d / max(stats.plays_last_30d, 1)
        f4 = 15.0 * min(velocity * 4, 1.0)
    b["trending"] = round(f4, 1)

    # ── Factor 5: Newness Boost (0–30 pts) ────────────────────────────────────
    # Full 30 pts for items added within 7 days (new content should never be frozen).
    # Linear decay from 30 → 0 between day 7 and day 30.
    # This ensures brand-new content always stays above the freeze threshold (25).
    f5 = 0.0
    if item.date_added:
        days_since_added = (now - _naive_utc(item.date_added)).total_seconds() / 86400
        if days_since_added <= 7:
            f5 = 30.0
        elif days_since_added < 30:
            f5 = 30.0 * (1.0 - (days_since_added - 7.0) / 23.0)
    b["newness"] = round(f5, 1)

    # ── Factor 6: Series Status (0–5 pts) ─────────────────────────────────────
    f6 = 5.0 if item.series_status == "continuing" else 0.0
    b["series_status"] = round(f6, 1)

    # ── Factor 7: Community Rating Bonus (0–5 pts) ────────────────────────────
    f7 = 0.0
    if item.community_rating and item.community_rating > 0:
        f7 = 5.0 * min(item.community_rating / 10.0, 1.0)
    b["community_rating"] = round(f7, 1)

    # ── Modifier: File size pressure (0 to −5 pts) ────────────────────────────
    size_gb = item.file_size_bytes / (1024 ** 3)
    penalty = min((size_gb - 5) * 0.5, 5.0) if size_gb > 5 else 0.0
    b["size_penalty"] = round(-penalty, 1)

    raw = f1 + f2 + f3 + f4 + f5 + f6 + f7 - penalty
    score = max(0.0, min(100.0, raw))
    return score, b


def calculate_temperature(item: ItemMeta, stats: PlaybackStats) -> float:
    """Calculate temperature score. See calculate_temperature_with_breakdown for details."""
    score, _ = calculate_temperature_with_breakdown(item, stats)
    return score
