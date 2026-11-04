"""``key=value`` metrics in stdout, e.g. ``[step 1200] loss=0.41 acc: 0.87 lr=3e-4``."""

import re

from pulse.metrics.model import Point

_STEP = re.compile(r"\b(?:global_step|step|iter(?:ation)?)\s*[=:\s]\s*(\d+)", re.IGNORECASE)
_PAIR = re.compile(
    r"(?<![\w/.-])([A-Za-z][\w./-]{0,63})\s*[=:]\s*"
    r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[-+]?(?:nan|inf(?:inity)?))(?![\w.])",
    re.IGNORECASE,
)
_AXES = {"step", "global_step", "iter", "iteration", "epoch", "batch", "time", "eta", "elapsed"}


def parse_log_metrics(lines: list[str]) -> list[Point]:
    """Metrics on lines that carry a step number; without one a line can't be
    placed on the x-axis, and repeated reads of the same tail would duplicate it."""
    points = []
    for line in lines:
        step_match = _STEP.search(line)
        if not step_match:
            continue
        step = int(step_match.group(1))
        for name, raw in _PAIR.findall(line):
            if name.lower() not in _AXES:
                points.append(Point(name, float(raw), step))  # NaN/Inf kept for alerts
    return points
