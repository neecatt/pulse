"""A simulated cluster so the app runs end to end without Slurm access.

Each account gets a deterministic set of jobs whose states advance with wall
time: within a few minutes of startup jobs start, finish, fail and approach
their time limit, and a new sweep job is submitted every 15 minutes. That is
enough to exercise the poller, events and push notifications locally.
"""

import math
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pulse.domain import Clock, JobState
from pulse.slurm.base import AccountRef, AccountSnapshot, JobTelemetry, SlurmError, SlurmJob

SWEEP_PERIOD_S = 15 * 60
LOOKBACK = timedelta(hours=24)
UNREACHABLE_SUFFIX = ".invalid"


@dataclass(frozen=True, slots=True)
class _ScriptedJob:
    offset: int  # submit time relative to the client's start, seconds
    wait_s: int
    run_s: int
    limit_s: int
    name: str
    partition: str
    nodes: int
    gpus: int
    outcome: JobState = JobState.COMPLETED
    reason: str | None = None
    exit_code: int = 0
    log_freezes_after_s: int | None = None  # simulates a hung training loop


_SCRIPT = (
    _ScriptedJob(-14 * 3600, 600, 20 * 3600, 24 * 3600, "llama-7b-sft", "gpu", 8, 32),
    _ScriptedJob(-3 * 3600, 120, 9 * 3600, 12 * 3600, "vit-l-pretrain", "gpu", 4, 16),
    _ScriptedJob(-1800, 1860, 3 * 3600, 8 * 3600, "diffusion-ft", "gpu", 2, 8),
    _ScriptedJob(-5650, 30, 5700, 6300, "gnn-sweep-17", "gpu", 1, 4),
    _ScriptedJob(
        -2400,
        60,
        2580,
        7200,
        "mixtral-eval",
        "gpu-small",
        1,
        8,
        outcome=JobState.FAILED,
        reason="OUT_OF_MEMORY",
        exit_code=137,
    ),
    _ScriptedJob(-6 * 3600, 300, 2 * 3600, 4 * 3600, "tokenizer-build", "cpu", 1, 0),
    _ScriptedJob(-600, 30, 6 * 3600, 8 * 3600, "rl-ppo", "gpu", 1, 4, log_freezes_after_s=300),
)


class MockSlurmClient:
    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._epoch = self._clock()

    public_key: str | None = None

    async def check(self, account: AccountRef) -> str | None:
        if account.host.endswith(UNREACHABLE_SUFFIX):
            raise SlurmError(f"SSH to {account.host} failed: host unreachable")
        return None

    async def close(self) -> None:
        return None

    async def snapshot(self, account: AccountRef) -> AccountSnapshot:
        await self.check(account)
        now = self._clock()
        seed = zlib.crc32(f"{account.username}@{account.host}".encode())
        jobs: list[SlurmJob] = []
        telemetry: dict[str, JobTelemetry] = {}
        for index, script in enumerate(self._scripts(now)):
            slurm_id = str(1_000_000 + seed % 8_000_000 + index)
            job = self._job_at(script, slurm_id, now)
            if job is None:
                continue
            jobs.append(job)
            if job.state is JobState.RUNNING:
                telemetry[slurm_id] = self._telemetry(script, job, now, seed)
        return AccountSnapshot(jobs=jobs, telemetry=telemetry)

    def _scripts(self, now: datetime) -> list[_ScriptedJob]:
        elapsed = int((now - self._epoch).total_seconds())
        sweeps = [
            _ScriptedJob(
                n * SWEEP_PERIOD_S + 45, 60, 600, 1800, f"hparam-sweep-{n:02d}", "gpu", 1, 2
            )
            for n in range(elapsed // SWEEP_PERIOD_S + 1)
        ]
        return [*_SCRIPT, *sweeps]

    def _job_at(self, s: _ScriptedJob, slurm_id: str, now: datetime) -> SlurmJob | None:
        submit = self._epoch + timedelta(seconds=s.offset)
        start = submit + timedelta(seconds=s.wait_s)
        end = start + timedelta(seconds=s.run_s)
        if now < submit or end < now - LOOKBACK:
            return None
        if now < start:
            state, elapsed = JobState.PENDING, 0
        elif now < end:
            state, elapsed = JobState.RUNNING, int((now - start).total_seconds())
        else:
            state, elapsed = s.outcome, s.run_s
        started = state is not JobState.PENDING
        return SlurmJob(
            slurm_id=slurm_id,
            name=s.name,
            partition=s.partition,
            state=state,
            reason=s.reason if state.is_terminal else ("Priority" if not started else None),
            nodes=s.nodes,
            gpus=s.gpus,
            node_list=f"gpu[{int(slurm_id) % 900:03d}-{int(slurm_id) % 900 + s.nodes - 1:03d}]"
            if started
            else None,
            submit_time=submit,
            start_time=start if started else None,
            end_time=end if state.is_terminal else None,
            time_limit_s=s.limit_s,
            elapsed_s=elapsed,
            exit_code=s.exit_code if state.is_terminal else None,
        )

    @staticmethod
    def _telemetry(s: _ScriptedJob, job: SlurmJob, now: datetime, seed: int) -> JobTelemetry:
        assert job.start_time is not None
        live_s = job.elapsed_s
        if s.log_freezes_after_s is not None:
            live_s = min(live_s, s.log_freezes_after_s)
        progress = live_s / s.run_s
        wobble = math.sin(live_s / 97 + seed % 7)
        loss = round(0.28 + 2.3 * math.exp(-4.5 * progress) + 0.03 * wobble, 4)
        epochs = 10
        epoch = f"{min(epochs, 1 + int(progress * epochs))}/{epochs}"
        step = live_s * 3
        log_tail = [
            f"[step {step - 30 * i}] epoch {epoch} loss={loss + 0.002 * i:.4f} lr=2.0e-05"
            for i in reversed(range(8))
        ]
        frozen = s.log_freezes_after_s is not None and job.elapsed_s > s.log_freezes_after_s
        return JobTelemetry(
            loss=loss,
            epoch=epoch,
            gpu_util=(round(88 + 8 * wobble, 1) if not frozen else 0.0) if job.gpus else None,
            gpu_mem=round(72 + 6 * math.cos(live_s / 131), 1) if job.gpus else None,
            log_tail=log_tail,
            log_updated_at=job.start_time + timedelta(seconds=live_s) if frozen else now,
        )
