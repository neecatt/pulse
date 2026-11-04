from datetime import UTC, datetime, timedelta

from pulse.domain import EventKind, JobState
from pulse.services.events import (
    format_duration,
    is_near_time_limit,
    is_stalled,
    state_change_event,
)
from pulse.slurm.base import JobTelemetry, SlurmJob


def job(state: JobState, **kwargs: object) -> SlurmJob:
    return SlurmJob(slurm_id="1", name="train", partition="gpu", state=state, **kwargs)  # type: ignore[arg-type]


def kind(prev: JobState | None, current: SlurmJob) -> EventKind | None:
    event = state_change_event(prev, current)
    return event.kind if event else None


def test_start_and_finish_transitions() -> None:
    assert kind(JobState.PENDING, job(JobState.RUNNING)) is EventKind.JOB_STARTED
    assert kind(JobState.RUNNING, job(JobState.COMPLETED)) is EventKind.JOB_COMPLETED
    assert kind(JobState.RUNNING, job(JobState.FAILED)) is EventKind.JOB_FAILED
    assert kind(JobState.RUNNING, job(JobState.TIMEOUT)) is EventKind.JOB_FAILED
    assert kind(JobState.PENDING, job(JobState.CANCELLED)) is EventKind.JOB_CANCELLED


def test_unchanged_and_requeued_jobs_are_silent() -> None:
    assert kind(JobState.RUNNING, job(JobState.RUNNING)) is None
    assert kind(JobState.COMPLETED, job(JobState.RUNNING)) is None
    assert kind(JobState.FAILED, job(JobState.PENDING)) is None
    assert kind(None, job(JobState.PENDING)) is None


def test_job_first_seen_after_finishing_is_announced() -> None:
    assert kind(None, job(JobState.COMPLETED, elapsed_s=90)) is EventKind.JOB_COMPLETED


def test_failure_message_includes_reason() -> None:
    event = state_change_event(JobState.RUNNING, job(JobState.FAILED, reason="OUT_OF_MEMORY"))
    assert event is not None
    assert event.message == "train failed — OUT_OF_MEMORY"


def test_near_time_limit() -> None:
    assert is_near_time_limit(job(JobState.RUNNING, elapsed_s=90, time_limit_s=100), 0.9)
    assert not is_near_time_limit(job(JobState.RUNNING, elapsed_s=89, time_limit_s=100), 0.9)
    assert not is_near_time_limit(job(JobState.RUNNING, elapsed_s=90), 0.9)
    assert not is_near_time_limit(job(JobState.PENDING, elapsed_s=90, time_limit_s=100), 0.9)


def test_is_stalled() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    window = timedelta(minutes=15)
    assert is_stalled(JobTelemetry(log_updated_at=now - window), now, window)
    assert not is_stalled(JobTelemetry(log_updated_at=now - window / 2), now, window)
    assert not is_stalled(JobTelemetry(), now, window)
    assert not is_stalled(None, now, window)


def test_format_duration() -> None:
    assert format_duration(59) == "0m"
    assert format_duration(3 * 3600 + 5 * 60) == "3h 05m"
