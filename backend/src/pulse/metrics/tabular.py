"""JSON-lines and CSV metric logs."""

import csv
import io
import json
import math
from datetime import UTC, datetime
from typing import Any

from pulse.metrics.hparams import flatten
from pulse.metrics.model import ParsedChunk, Point

STEP_KEYS = ("step", "global_step", "_step", "iteration", "iter")
TIME_KEYS = ("time", "timestamp", "_timestamp", "wall_time")
HPARAM_KEYS = ("hparams", "config", "params")


def parse_jsonl(data: bytes) -> ParsedChunk:
    """One JSON object per line. Numeric fields become metrics; a ``step``-like
    field is the x-axis; an ``hparams``/``config`` object holds hyperparameters."""
    chunk = ParsedChunk()
    lines, chunk.consumed = _complete_lines(data)
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        for key in HPARAM_KEYS:
            if isinstance(record.get(key), dict):
                chunk.hparams.update(flatten(record.pop(key)))
        chunk.points.extend(_record_points(record))
    return chunk


def parse_csv(data: bytes, header: list[str] | None) -> tuple[ParsedChunk, list[str] | None]:
    """CSV with a header row. ``header`` is the one read on an earlier chunk."""
    chunk = ParsedChunk()
    lines, chunk.consumed = _complete_lines(data)
    rows = list(csv.reader(io.StringIO("\n".join(lines))))
    if header is None and rows:
        header, rows = [h.strip() for h in rows[0]], rows[1:]
    if header is None:
        return chunk, None
    for row in rows:
        if len(row) == len(header):
            chunk.points.extend(_record_points(dict(zip(header, row, strict=True))))
    return chunk, header


def _record_points(record: dict[str, Any]) -> list[Point]:
    step = next((_as_int(record[k]) for k in STEP_KEYS if k in record), None)
    wall = next((_as_time(record[k]) for k in TIME_KEYS if k in record), None)
    skip = {*STEP_KEYS, *TIME_KEYS}
    points = []
    for key, raw in record.items():
        value = _as_float(raw)
        if key not in skip and value is not None:
            points.append(Point(key, value, step, wall))
    return points


def _complete_lines(data: bytes) -> tuple[list[str], int]:
    end = data.rfind(b"\n") + 1  # a trailing partial line waits for the next read
    text = data[:end].decode("utf-8", "replace")
    return [line for line in text.splitlines() if line.strip()], end


def _as_float(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _as_int(raw: Any) -> int | None:
    value = _as_float(raw)
    return int(value) if value is not None else None


def _as_time(raw: Any) -> datetime | None:
    value = _as_float(raw)
    if value is None or not 1e9 < value < 1e10:  # plausible Unix seconds only
        return None
    return datetime.fromtimestamp(value, UTC)
