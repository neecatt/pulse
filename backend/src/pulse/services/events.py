"""Turn successive job snapshots into user-facing events. Pure logic; no I/O."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from pulse.domain import EventKind, JobState
from pulse.slurm.base import JobTelemetry, SlurmJob


@dataclass(frozen=True, slots=True)
class DetectedEvent:
    slurm_id: str
    kind: EventKind
    message: str


_TERMINAL_EVENTS: dict[JobState, EventKind] = {
    JobState.COMPLETED: EventKind.JOB_COMPLETED,
    JobState.FAILED: EventKind.JOB_FAILED,
    JobState.TIMEOUT: EventKind.JOB_FAILED,
    JobState.CANCELLED: EventKind.JOB_CANCELLED,
}


def state_change_event(prev: JobState | None, job: SlurmJob) -> DetectedEvent | None:
    """Event for a state transition, or None if the change isn't worth announcing.

    ``prev`` is None for a job seen for the first time. Moves out of a terminal
    state (e.g. a requeue) are silent; the following start is announced instead.
    """
    if prev == job.state or (prev is not None and prev.is_terminal):
        return None
    if job.state is JobState.RUNNING:
        where = f" on {job.node_list}" if job.node_list else ""
        return DetectedEvent(job.slurm_id, EventKind.JOB_STARTED, f"{job.name} started{where}")
    kind = _TERMINAL_EVENTS.get(job.state)
    if kind is None:
        return None
    return DetectedEvent(job.slurm_id, kind, _terminal_message(job))


def _terminal_message(job: SlurmJob) -> str:
    match job.state:
        case JobState.COMPLETED:
            return f"{job.name} completed in {format_duration(job.elapsed_s)}"
        case JobState.CANCELLED:
            return f"{job.name} was cancelled"
        case JobState.TIMEOUT:
            return f"{job.name} hit its time limit"
        case _:
            detail = job.reason or (f"exit code {job.exit_code}" if job.exit_code else "")
            return f"{job.name} failed" + (f" — {detail}" if detail else "")


def is_near_time_limit(job: SlurmJob, ratio: float) -> bool:
    return (
        job.state is JobState.RUNNING
        and job.time_limit_s is not None
        and job.elapsed_s >= ratio * job.time_limit_s
    )


def is_stalled(telemetry: JobTelemetry | None, now: datetime, stall_after: timedelta) -> bool:
    return (
        telemetry is not None
        and telemetry.log_updated_at is not None
        and now - telemetry.log_updated_at >= stall_after
    )


def format_duration(seconds: int) -> str:
    hours, rest = divmod(max(seconds, 0), 3600)
    minutes = rest // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"
