from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional

Rating = Literal["again", "hard", "good", "easy"]


@dataclass(frozen=True)
class Sm2Result:
    ease: float
    interval_days: int
    repetitions: int
    next_review_at: datetime


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sm2_update(learning: Optional[Dict[str, Any]], rating: Rating, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Compute an SM-2-style update patch for the `learning` map.

    Expects (but does not require) fields:
      - ease (float)
      - intervalDays (int)
      - repetitions (int)

    Returns a dict suitable for `update_word_learning`, including:
      - known, ease, intervalDays, repetitions, lastReviewedAt, nextReviewAt
    """
    if now is None:
        now = _now_utc()

    learning = learning or {}
    try:
        ease = float(learning.get("ease", 2.5))
    except Exception:
        ease = 2.5

    try:
        interval_days = int(learning.get("intervalDays", 0) or 0)
    except Exception:
        interval_days = 0

    try:
        repetitions = int(learning.get("repetitions", 0) or 0)
    except Exception:
        repetitions = 0

    q_map = {"again": 0, "hard": 3, "good": 4, "easy": 5}
    q = q_map[rating]

    if q < 3:
        repetitions = 0
        interval_days = 1
    else:
        if repetitions == 0:
            interval_days = 1
        elif repetitions == 1:
            interval_days = 6
        else:
            interval_days = max(1, int(round(interval_days * ease)))
        repetitions += 1

    ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    ease = max(1.3, float(ease))

    next_review_at = now + timedelta(days=int(interval_days))

    return {
        "known": True,
        "ease": ease,
        "intervalDays": int(interval_days),
        "repetitions": int(repetitions),
        "lastReviewedAt": now,
        "nextReviewAt": next_review_at,
    }
