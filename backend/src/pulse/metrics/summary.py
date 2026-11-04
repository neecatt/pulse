"""Running per-metric summaries, so alerts and tables never re-scan history."""

import math
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pulse.constants import EMA_WEIGHT, IMPROVEMENT_RATIO
from pulse.metrics.model import Point

# last, min, max, first, n, step, best_at (ISO time), ema (smoothed value) and
# ema_min (best smoothed value, which a single lucky batch can't drag down).
Summary = dict[str, Any]


def update_summaries(
    summaries: dict[str, Summary], points: Iterable[Point], now: datetime
) -> dict[str, Summary]:
    """Fold new points into per-metric summaries and return the new mapping.

    Points at or before a metric's last summarised step are skipped, because the
    same stdout lines are re-read on every poll.
    """
    out = {name: dict(s) for name, s in summaries.items()}
    ordered = sorted(points, key=lambda p: (p.step is None, p.step or 0))
    for point in ordered:
        if not math.isfinite(point.value):
            continue
        s = out.get(point.name)
        last_step = s.get("step") if s is not None else None
        if point.step is not None and last_step is not None and point.step <= last_step:
            continue
        moment = (point.wall_time or now).isoformat()
        if s is None:
            out[point.name] = {
                "first": point.value,
                "last": point.value,
                "min": point.value,
                "max": point.value,
                "n": 1,
                "ema": point.value,
                "ema_min": point.value,
                "step": point.step,
                "best_at": moment,
            }
            continue
        if point.value < s["min"] - max(abs(s["min"]) * IMPROVEMENT_RATIO, 1e-12):
            s["best_at"] = moment
        s["min"] = min(s["min"], point.value)
        s["max"] = max(s["max"], point.value)
        s["last"] = point.value
        s["n"] += 1
        s["ema"] = EMA_WEIGHT * s["ema"] + (1 - EMA_WEIGHT) * point.value
        s["ema_min"] = min(s.get("ema_min", s["ema"]), s["ema"])
        s["step"] = point.step if point.step is not None else s.get("step")
    return out
