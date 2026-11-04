"""Background loop that refreshes job snapshots and records events."""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from pulse.config import Settings
from pulse.domain import Clock, EventKind, JobState
from pulse.metrics.ingest import ingest_files, load_cursors, store_points
from pulse.metrics.logs import parse_log_metrics
from pulse.metrics.model import Point
from pulse.models import Account, Event, Job, User, utcnow
from pulse.schemas import EventOut, Monitoring
from pulse.services.broadcaster import Broadcaster
from pulse.services.events import (
    DetectedEvent,
    is_near_time_limit,
    is_stalled,
    state_change_event,
)
from pulse.services.notifier import Notifier
from pulse.slurm import AccountRef, AccountSnapshot, JobTelemetry, SlurmClient, SlurmError, SlurmJob

logger = logging.getLogger(__name__)

# How often the scheduler checks which accounts are due. Bounds the fastest
# refresh a user can choose.
TICK_SECONDS = 5


@dataclass(slots=True)
class PollResult:
    user_id: int
    account_id: int
    events: list[dict[str, Any]] = field(default_factory=list)


class Poller:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        client: SlurmClient,
        notifier: Notifier,
        broadcaster: Broadcaster,
        settings: Settings,
        clock: Clock = utcnow,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._client = client
        self._notifier = notifier
        self._broadcaster = broadcaster
        self._settings = settings
        self._wakeup = asyncio.Event()

    def trigger(self) -> None:
        """Run the next poll now instead of waiting for the interval."""
        self._wakeup.set()

    async def run_forever(self) -> None:
        force = True  # poll everything at startup
        while True:
            try:
                await self.poll_all(force=force)
            except Exception:
                logger.exception("poll cycle failed")
            force = False
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wakeup.wait(), TICK_SECONDS)
                force = True  # trigger(): new account, app opened, settings changed
            self._wakeup.clear()

    def interval_for(self, user: User) -> int:
        """Seconds between polls of a user's accounts: fast while they're watching."""
        monitoring = Monitoring.resolve(user.monitoring_prefs, self._settings)
        if self._broadcaster.has_subscribers_for(user.id):
            return monitoring.live_refresh_seconds
        return monitoring.idle_refresh_seconds

    async def poll_all(self, *, force: bool = True) -> None:
        """Poll every direct account that is due (or all of them when forced)."""
        now = self._clock()
        async with self._sessions() as session:
            direct = await session.scalars(
                select(Account)
                .where(Account.connection == "direct")
                .options(selectinload(Account.user))
            )
            account_ids = [a.id for a in direct if force or self._is_due(a, now)]
            stale = await self._flag_silent_agents(session)
        limit = asyncio.Semaphore(self._settings.poll_concurrency)

        async def guarded(account_id: int) -> PollResult | None:
            async with limit:
                return await self.poll_account(account_id)

        results = await asyncio.gather(*(guarded(i) for i in account_ids))
        self._publish([r for r in results if r is not None] + stale)

    async def _flag_silent_agents(self, session: AsyncSession) -> list[PollResult]:
        """Agent accounts don't get polled, so notice when one stops reporting."""
        cutoff = self._clock() - timedelta(seconds=self._settings.agent_stale_seconds)
        silent = await session.scalars(
            select(Account).where(
                Account.connection == "agent",
                Account.last_polled_at < cutoff,
                Account.last_error.is_(None),
            )
        )
        results = []
        for account in silent:
            account.last_error = (
                f"The agent on {account.cluster} stopped reporting. "
                "Check it with `python3 ~/.pulse-agent.py status` on the login node."
            )
            results.append(PollResult(user_id=account.user_id, account_id=account.id))
        await session.commit()
        return results

    def _publish(self, results: list[PollResult]) -> None:
        """One live update per user per cycle, so clients refetch once."""
        by_user: dict[int, list[PollResult]] = {}
        for result in results:
            by_user.setdefault(result.user_id, []).append(result)
        for user_id, items in by_user.items():
            self._broadcaster.publish(
                user_id,
                {
                    "type": "update",
                    "accounts": [r.account_id for r in items],
                    "events": [e for r in items for e in r.events],
                },
            )

    async def poll_account(self, account_id: int) -> PollResult | None:
        """Fetch a snapshot from the cluster and ingest it."""
        async with self._sessions() as session:
            account = await session.get(Account, account_id)
            if account is None:
                return None
            ref = AccountRef(
                username=account.username,
                host=account.host,
                port=account.port,
                host_key=account.host_key,
            )
            cursors = await load_cursors(session, account_id)
        try:
            snapshot: AccountSnapshot | SlurmError = await self._client.snapshot(ref, cursors)
        except SlurmError as exc:
            logger.info("account %s unreachable: %s", account_id, exc)
            snapshot = exc
        return await self.ingest(account_id, snapshot)

    async def ingest_and_publish(
        self, account_id: int, snapshot: AccountSnapshot | SlurmError
    ) -> PollResult | None:
        """Ingest a snapshot pushed by an agent and notify live clients at once."""
        result = await self.ingest(account_id, snapshot)
        if result is not None:
            self._publish([result])
        return result

    async def ingest(
        self, account_id: int, snapshot: AccountSnapshot | SlurmError
    ) -> PollResult | None:
        """Store a snapshot (or the error that prevented one), record events and
        send notifications. Shared by polling and agent reports."""
        async with self._sessions() as session:
            account = await session.get(
                Account,
                account_id,
                options=[
                    selectinload(Account.jobs).selectinload(Job.metric_files),
                    selectinload(Account.user),
                ],
            )
            if account is None:
                return None
            now = self._clock()
            result = PollResult(user_id=account.user_id, account_id=account.id)
            if isinstance(snapshot, SlurmError):
                account.last_error = str(snapshot)[:500]
                account.last_polled_at = now
                await session.commit()
                return result

            # The first snapshot of an account only records its jobs; announcing
            # every pre-existing job as "started" would flood the user.
            announce = account.last_polled_at is not None
            events = await self._apply_snapshot(session, account, snapshot, now, announce=announce)
            account.last_polled_at = now
            account.last_error = None
            account.host_key = account.host_key or snapshot.host_key
            await session.commit()

            result.events = [EventOut.model_validate(e).model_dump(mode="json") for e in events]
            if events and account.notify:
                await self._notifier.send_events(session, account.user_id, events)
            return result

    def _is_due(self, account: Account, now: datetime) -> bool:
        if account.last_polled_at is None:
            return True
        # A tick of slack so a 10 s interval doesn't slip to 15 s on a 5 s tick.
        elapsed = (now - account.last_polled_at).total_seconds()
        return elapsed + TICK_SECONDS / 2 >= self.interval_for(account.user)

    async def _apply_snapshot(
        self,
        session: AsyncSession,
        account: Account,
        snapshot: AccountSnapshot,
        now: datetime,
        *,
        announce: bool,
    ) -> list[Event]:
        rows = {job.slurm_id: job for job in account.jobs}
        monitoring = Monitoring.resolve(account.user.monitoring_prefs, self._settings)
        events: list[Event] = []
        new_points: list[tuple[Job, list[Point]]] = []
        for slurm_job in snapshot.jobs:
            row = rows.get(slurm_job.slurm_id)
            previous_state = row.state if row else None
            if row is None:
                # Column defaults apply only on INSERT; set what's read before then.
                row = Job(slurm_id=slurm_job.slurm_id, metric_files=[], hparams={}, tags=[])
                account.jobs.append(row)
            _copy_job_fields(row, slurm_job)

            telemetry = snapshot.telemetry.get(slurm_job.slurm_id)
            if telemetry is not None:
                new_points.append((row, _record_telemetry(row, telemetry)))

            detected = self._detect(row, slurm_job, previous_state, telemetry, now, monitoring)
            if announce:
                events.extend(
                    Event(account=account, job=row, kind=d.kind, message=d.message)
                    for d in detected
                )
        session.add_all(events)
        await session.flush()  # new jobs need ids before their points are stored
        for row, points in new_points:
            await store_points(session, row, points, now)
        return events

    def _detect(
        self,
        row: Job,
        job: SlurmJob,
        previous_state: JobState | None,
        telemetry: JobTelemetry | None,
        now: datetime,
        monitoring: Monitoring,
    ) -> list[DetectedEvent]:
        detected: list[DetectedEvent] = []
        if change := state_change_event(previous_state, job):
            detected.append(change)

        warn_ratio = monitoring.time_limit_warning_percent / 100
        if not row.warned_time_limit and is_near_time_limit(job, warn_ratio):
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
            stall_minutes = monitoring.stall_minutes
            stalled = is_stalled(telemetry, now, timedelta(minutes=stall_minutes))
            if stalled and not row.warned_stall:
                detected.append(
                    DetectedEvent(
                        job.slurm_id,
                        EventKind.JOB_STALLED,
                        f"{job.name} has written no output for {stall_minutes}+ minutes",
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


def _record_telemetry(row: Job, t: JobTelemetry) -> list[Point]:
    """Update the job's live fields and return its new metric points."""
    log_advanced = t.log_updated_at is not None and t.log_updated_at != row.log_updated_at
    points: list[Point] = []
    # Only read the log when it moved, so a hung job doesn't draw a flat line.
    if log_advanced:
        points = parse_log_metrics(t.log_tail)
        if not points and t.loss is not None:
            points = [Point("loss", t.loss)]  # loss without a step number
    points.extend(
        Point(name, value)
        for name, value in (("gpu_util", t.gpu_util), ("gpu_mem", t.gpu_mem))
        if value is not None
    )
    points.extend(ingest_files(row, t.files))

    row.epoch = t.epoch or row.epoch
    if row.primary_metric is None and t.loss is not None:
        row.last_loss = t.loss
    # GPU usage is sampled less often than jobs are polled; keep the last reading.
    row.gpu_util = t.gpu_util if t.gpu_util is not None else row.gpu_util
    row.gpu_mem = t.gpu_mem if t.gpu_mem is not None else row.gpu_mem
    if t.log_tail:
        row.log_tail = t.log_tail
    row.log_updated_at = t.log_updated_at
    return points
