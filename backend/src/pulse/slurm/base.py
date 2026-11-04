from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from pulse.domain import JobState


@dataclass(frozen=True, slots=True)
class AccountRef:
    """What a Slurm client needs to reach one account."""

    username: str
    host: str
    port: int = 22


@dataclass(frozen=True, slots=True)
class SlurmJob:
    slurm_id: str
    name: str
    partition: str
    state: JobState
    reason: str | None = None
    nodes: int = 0
    gpus: int = 0
    node_list: str | None = None
    submit_time: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    time_limit_s: int | None = None
    elapsed_s: int = 0
    exit_code: int | None = None


@dataclass(frozen=True, slots=True)
class JobTelemetry:
    """Best-effort live data for a running job. Any field may be unknown."""

    loss: float | None = None
    epoch: str | None = None
    gpu_util: float | None = None
    gpu_mem: float | None = None
    log_tail: list[str] = field(default_factory=list)
    log_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    jobs: list[SlurmJob]
    telemetry: dict[str, JobTelemetry] = field(default_factory=dict)  # keyed by slurm_id


class SlurmError(Exception):
    """Raised when a cluster can't be reached or returns unusable output."""


class SlurmClient(Protocol):
    async def check(self, account: AccountRef) -> None:
        """Verify the account is reachable; raise SlurmError otherwise."""

    async def snapshot(self, account: AccountRef) -> AccountSnapshot:
        """Active and recently finished jobs, plus telemetry for running ones."""
