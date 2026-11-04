"""A simulated cluster so the app runs end to end without Slurm access.

Each account gets a deterministic set of jobs whose states advance with wall
time: within a few minutes of startup jobs start, finish, fail and approach
their time limit, and a new sweep job is submitted every 15 minutes. That is
enough to exercise the poller, events and push notifications locally.
"""

import json
import math
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pulse.domain import Clock, JobState
from pulse.metrics.discovery import CHUNK_BYTES
from pulse.slurm.base import (
    AccountRef,
    AccountSnapshot,
    Cursors,
    FileChunk,
    GpuStats,
    JobTelemetry,
    NodeStats,
    SlurmError,
    SlurmJob,
)
from pulse.slurm.parsing import mean_gpu_usage

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

    async def snapshot(self, account: AccountRef, cursors: Cursors) -> AccountSnapshot:
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
                files = _metric_files(account, script, job, cursors.get(slurm_id, {}))
                telemetry[slurm_id] = self._telemetry(script, job, now, seed, files)
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
    def _telemetry(
        s: _ScriptedJob, job: SlurmJob, now: datetime, seed: int, files: list[FileChunk]
    ) -> JobTelemetry:
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
        nodes = _node_stats(s, job, live_s, frozen)
        gpu_util, gpu_mem = mean_gpu_usage(nodes)
        return JobTelemetry(
            loss=loss,
            epoch=epoch,
            gpu_util=gpu_util,
            gpu_mem=gpu_mem,
            nodes=nodes,
            log_tail=log_tail,
            log_updated_at=job.start_time + timedelta(seconds=live_s) if frozen else now,
            files=files,
        )


def _node_stats(s: _ScriptedJob, job: SlurmJob, live_s: int, frozen: bool) -> dict[str, NodeStats]:
    """Plausible per-node CPU, memory and per-GPU usage; one node runs a bit cooler."""
    first = int(job.slurm_id) % 900
    gpus_per_node = s.gpus // max(s.nodes, 1)
    nodes: dict[str, NodeStats] = {}
    for n in range(s.nodes):
        wobble = math.sin(live_s / 97 + n)
        cool = 12 if n == s.nodes - 1 and s.nodes > 1 else 0  # e.g. a data-loading straggler
        gpus: list[GpuStats] = [
            {
                "util": 0.0 if frozen else round(min(100, 90 + 6 * wobble - cool - g), 1),
                "mem": round(70 + 5 * math.cos(live_s / 131 + g), 1),
            }
            for g in range(gpus_per_node)
        ]
        nodes[f"gpu{first + n:03d}"] = {
            "cpu": round(5 if frozen else 55 + 20 * wobble, 1),
            "mem": round(48 + 4 * math.cos(live_s / 211 + n), 1),
            "gpus": gpus,
        }
    return nodes


METRIC_INTERVAL_S = 60  # one metrics.jsonl record per simulated minute
VAL_EVERY = 5


def _metric_files(
    account: AccountRef, s: _ScriptedJob, job: SlurmJob, cursors: Mapping[str, int]
) -> list[FileChunk]:
    """A growing metrics.jsonl and a config.yaml, like a real training script writes."""
    run_dir = f"/scratch/{account.username}/{s.name}"
    live_s = (
        job.elapsed_s
        if s.log_freezes_after_s is None
        else min(job.elapsed_s, s.log_freezes_after_s)
    )
    # Per account and job, so the same experiment on two accounts differs a little.
    salt = zlib.crc32(f"{account.username}/{s.name}".encode()) % 100 / 100
    rate, floor = 3.5 + 2 * salt, 0.2 + 0.25 * salt  # each run learns a bit differently
    lines = []
    for k in range(live_s // METRIC_INTERVAL_S + 1):
        p = k * METRIC_INTERVAL_S / s.run_s
        record: dict[str, float | int] = {
            "step": k * 180,
            "train/loss": round(
                floor + 2.2 * math.exp(-rate * p) + 0.04 * math.sin(k / 3 + salt), 4
            ),
            "train/acc": round(min(0.99, 0.35 + (0.65 - floor / 2) * (1 - math.exp(-rate * p))), 4),
            "lr": round(3e-4 * min(1.0, p * 20) * (0.5 + 0.5 * math.cos(math.pi * p)), 8),
        }
        if k % VAL_EVERY == 0:
            record["val/loss"] = round(floor + 0.08 + 2.1 * math.exp(-0.9 * rate * p), 4)
            record["val/acc"] = round(
                min(0.97, 0.3 + (0.62 - floor / 2) * (1 - math.exp(-0.8 * rate * p))), 4
            )
        lines.append(json.dumps(record, sort_keys=True))
    metrics = ("\n".join(lines) + "\n").encode()
    config = (
        f"model: {s.name.split('-')[0]}\n"
        f"optimizer:\n  name: adamw\n  lr: 3.0e-4\n  weight_decay: {0.01 + salt / 10:.3f}\n"
        f"batch_size: {2 ** (5 + int(salt * 4))}\n"
        f"seed: {int(salt * 1000)}\n"
        f"gpus: {s.gpus}\n"
    ).encode()

    chunks = []
    for name, data in (("metrics.jsonl", metrics), ("config.yaml", config)):
        path = f"{run_dir}/{name}"
        offset = cursors.get(path, 0)
        if name == "config.yaml":
            if offset == len(data):
                continue
            offset = 0
        if offset > len(data):
            offset = 0
        chunks.append(FileChunk(path, offset, len(data), data[offset : offset + CHUNK_BYTES]))
    return chunks
