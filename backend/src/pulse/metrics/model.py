from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Point:
    name: str
    value: float
    step: int | None = None
    wall_time: datetime | None = None


@dataclass(slots=True)
class ParsedChunk:
    points: list[Point] = field(default_factory=list)
    consumed: int = 0  # bytes fully parsed; the rest is re-read next time
    hparams: dict[str, Any] = field(default_factory=dict)
