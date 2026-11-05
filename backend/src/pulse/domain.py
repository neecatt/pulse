"""Domain vocabulary shared by the Slurm layer, services and API."""

from collections.abc import Callable, Mapping
from datetime import datetime
from enum import StrEnum

Clock = Callable[[], datetime]


class JobState(StrEnum):
    """Normalised Slurm job state. Raw Slurm states are folded into these."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"

    @property
    def is_terminal(self) -> bool:
        return self not in (JobState.PENDING, JobState.RUNNING)


class EventKind(StrEnum):
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"
    # Ran until its time limit. Often on purpose (train for 24 h, keep the best
    # checkpoint), so it's reported like an ending, not a failure.
    JOB_TIMED_OUT = "job_timed_out"
    JOB_TIME_LIMIT = "job_time_limit"
    JOB_STALLED = "job_stalled"
    JOB_NAN = "job_nan"
    JOB_DIVERGING = "job_diverging"
    JOB_PLATEAU = "job_plateau"


def resolve_alerts(stored: Mapping[str, bool]) -> dict[EventKind, bool]:
    """Alert preferences with every kind present; unset kinds default to enabled."""
    return {kind: stored.get(kind.value, True) for kind in EventKind}
