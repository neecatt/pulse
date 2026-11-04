"""Background loop that refreshes job snapshots and records events."""

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from pulse.config import Settings
from pulse.domain import Clock, EventKind, JobState
from pulse.models import Account, Event, Job, JobMetric, utcnow
from pulse.services.events import (
    DetectedEvent,
    is_near_time_limit,
    is_stalled,
    state_change_event,
)
from pulse.services.notifier import Notifier
from pulse.slurm import AccountRef, AccountSnapshot, JobTelemetry, SlurmClient, SlurmError, SlurmJob

logger = logging.getLogger(__name__)


class Poller:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        client: SlurmClient,
        notifier: Notifier,
        settings: Settings,
        clock: Clock = utcnow,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._client = client
        self._notifier = notifier
        self._settings = settings
        self._wakeup = asyncio.Event()

    def trigger(self) -> None:
        """Run the next poll now instead of waiting for the interval."""
        self._wakeup.set()

    async def run_forever(self) -> None:
        while True:
            try:
                await self.poll_all()
            except Exception:
                logger.exception("poll cycle failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wakeup.wait(), self._settings.poll_interval_seconds)
            self._wakeup.clear()

    async def poll_all(self) -> None:
        async with self._sessions() as session:
            account_ids = list(await session.scalars(select(Account.id)))
        limit = asyncio.Semaphore(self._settings.poll_concurrency)

        async def guarded(account_id: int) -> None:
            async with limit:
                await self.poll_account(account_id)

        await asyncio.gather(*(guarded(i) for i in account_ids))

    async def poll_account(self, account_id: int) -> None:
        async with self._sessions() as session:
            account = await session.get(
                Account,
                account_id,
                options=[selectinload(Account.jobs), selectinload(Account.user)],
            )
            if account is None:
                return
            now = self._clock()
            ref = AccountRef(username=account.username, host=account.host, port=account.port)
            try:
                snapshot = await self._client.snapshot(ref)
            except SlurmError as exc:
                logger.info("account %s unreachable: %s", account.id, exc)
                account.last_error = str(exc)[:500]
                account.last_polled_at = now
                await session.commit()
                return

            # The first poll of an account only records its jobs; announcing every
            # pre-existing job as "started" would flood the user.
            announce = account.last_polled_at is not None
            events = self._apply_snapshot(session, account, snapshot, now, announce=announce)
            account.last_polled_at = now
            account.last_error = None
            await session.commit()

            if events and account.notify:
                await self._notifier.send_events(session, account.user_id, events)

    def _apply_snapshot(
        self,
        session: AsyncSession,
        account: Account,
        snapshot: AccountSnapshot,
        now: datetime,
        *,
        announce: bool,
    ) -> list[Event]:
        rows = {job.slurm_id: job for job in account.jobs}
        events: list[Event] = []
        for slurm_job in snapshot.jobs:
            row = rows.get(slurm_job.slurm_id)
            previous_state = row.state if row else None
            if row is None:
                row = Job(slurm_id=slurm_job.slurm_id)
                account.jobs.append(row)
            _copy_job_fields(row, slurm_job)

            telemetry = snapshot.telemetry.get(slurm_job.slurm_id)
            if telemetry is not None:
                _record_telemetry(session, row, telemetry, now)

            detected = self._detect(row, slurm_job, previous_state, telemetry, now)
            if announce:
                events.extend(
                    Event(account=account, job=row, kind=d.kind, message=d.message)
                    for d in detected
                )
        session.add_all(events)
        return events

    def _detect(
        self,
        row: Job,
        job: SlurmJob,
        previous_state: JobState | None,
        telemetry: JobTelemetry | None,
        now: datetime,
    ) -> list[DetectedEvent]:
        s = self._settings
        detected: list[DetectedEvent] = []
        if change := state_change_event(previous_state, job):
            detected.append(change)

        if not row.warned_time_limit and is_near_time_limit(job, s.time_limit_warning_ratio):
            row.warned_time_limit = True
            assert job.time_limit_s is not None
            used = round(100 * job.elapsed_s / job.time_limit_s)
            detected.append(
                DetectedEvent(
                    job.slurm_id,
                    EventKind.JOB_TIME_LIMIT,
                    f"{job.name} has used {used}% of its time limit",
                )
            )

        if telemetry is not None and telemetry.log_updated_at is not None:
            stalled = is_stalled(telemetry, now, timedelta(minutes=s.stall_minutes))
            if stalled and not row.warned_stall:
                detected.append(
                    DetectedEvent(
                        job.slurm_id,
                        EventKind.JOB_STALLED,
                        f"{job.name} has written no output for {s.stall_minutes}+ minutes",
                    )
                )
            row.warned_stall = stalled
        return detected


def _copy_job_fields(row: Job, job: SlurmJob) -> None:
    row.name = job.name
    row.partition = job.partition
    row.state = job.state
    row.reason = job.reason
    row.nodes = job.nodes
    row.gpus = job.gpus
    row.node_list = job.node_list
    row.submit_time = job.submit_time
    row.start_time = job.start_time
    row.end_time = job.end_time
    row.time_limit_s = job.time_limit_s
    row.elapsed_s = job.elapsed_s
    row.exit_code = job.exit_code


def _record_telemetry(session: AsyncSession, row: Job, t: JobTelemetry, now: datetime) -> None:
    log_advanced = t.log_updated_at is not None and t.log_updated_at != row.log_updated_at
    samples: dict[str, float | None] = {"gpu_util": t.gpu_util, "gpu_mem": t.gpu_mem}
    # Only sample loss when the log moved, so a hung job doesn't draw a flat line.
    if log_advanced:
        samples["loss"] = t.loss
    session.add_all(
        JobMetric(job=row, name=name, ts=now, value=value)
        for name, value in samples.items()
        if value is not None
    )
    row.epoch = t.epoch or row.epoch
    row.last_loss = t.loss if t.loss is not None else row.last_loss
    row.gpu_util = t.gpu_util
    row.gpu_mem = t.gpu_mem
    if t.log_tail:
        row.log_tail = t.log_tail
    row.log_updated_at = t.log_updated_at
